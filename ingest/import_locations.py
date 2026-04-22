"""
import_locations.py
-------------------
Imports :Location nodes and :BORN_IN, :RESIDES_IN, :LOCATED_IN relationships
from the full character dataset.

Source fields:
  Origin    → :BORN_IN + :LOCATED_IN (sea→specific hierarchy)
  Residence → :RESIDES_IN {status: current|former|temporary}

Parsing rules:
  "East Blue"                         → BORN_IN East_Blue
  "East Blue(Foosha Village)"         → BORN_IN East_Blue + BORN_IN Foosha_Village
                                         + Foosha_Village LOCATED_IN East_Blue
  "Grand Line(Ryugu Kingdom;Fish-Man Island)"
                                      → BORN_IN Grand_Line + BORN_IN Ryugu_Kingdom
                                         + BORN_IN Fish_Man_Island
                                         + Ryugu_Kingdom LOCATED_IN Grand_Line
                                         + Fish_Man_Island LOCATED_IN Grand_Line
  Fused Residence ("ElbaphEnies Lobby(former)") → split + log to logs/residence_splits.log
  Sub-location parens stripped: "Shells Town(153rd Branch)(former)" → Shells_Town

Usage:
  python import_locations.py           # dry-run (no Neo4j writes)
  python import_locations.py --apply   # write to Neo4j
"""

import json
import re
import os
import sys
import argparse
from datetime import datetime
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATA_FILE = "data/full-character-data-processed-2.json"

ROOT = os.path.dirname(os.path.abspath(__file__))


# ── helpers ───────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"['’‘`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


_STATUS_MAP = {
    "former": "former",
    "formerly": "former",
    "temporary": "temporary",
    "temporarily": "temporary",
}

def extract_status(paren_contents: list[str]) -> str:
    for text in paren_contents:
        for tok in re.split(r"[\s,]+", text.lower()):
            if tok in _STATUS_MAP:
                return _STATUS_MAP[tok]
    return "current"


# ── Origin parsing ─────────────────────────────────────────────────────────────

def parse_origin(raw: str) -> list[dict]:
    """
    Returns list of {"name", "slug", "parent_slug"}.
    Sea location has parent_slug=None; specific locations have parent_slug=sea_slug.

    Inner separator is [;,] to handle both:
      "Grand Line(Ryugu Kingdom;Fish-Man Island)"
      "Grand Line(Ryugu Kingdom,Fish-Man Island)"
    """
    raw = re.sub(r"\[\d+\]", "", raw).strip()
    if not raw:
        return []

    if "(" not in raw:
        name = raw.strip()
        return [{"name": name, "slug": slugify(name), "parent_slug": None}]

    # Guard against malformed strings missing closing paren
    if ")" not in raw:
        name = raw[:raw.index("(")].strip()
        return [{"name": name, "slug": slugify(name), "parent_slug": None}]

    sea = raw[:raw.index("(")].strip()
    inner = raw[raw.index("(") + 1 : raw.rindex(")")].strip()
    sea_slug = slugify(sea)
    result = [{"name": sea, "slug": sea_slug, "parent_slug": None}]

    for specific in re.split(r"[;,]", inner):
        specific = specific.strip()
        if specific:
            result.append({
                "name": specific,
                "slug": slugify(specific),
                "parent_slug": sea_slug,
            })

    return result


# ── Residence parsing ──────────────────────────────────────────────────────────

def _split_fused(part: str) -> list[str]:
    """
    Split a fused residence string at fusion boundaries:
      1. )(UppercaseLetter) — closing paren immediately before an uppercase letter
      2. [a-z][A-Z]        — camelCase boundary with no separator
    Returns a list of 1+ parts. Log caller handles recording the split.
    """
    # Pattern 1: )(Uppercase)
    sub = re.split(r"(?<=\))(?=[A-Z])", part)
    if len(sub) > 1:
        return [s.strip() for s in sub if s.strip()]
    # Pattern 2: camelCase boundary
    sub = re.split(r"(?<=[a-z])(?=[A-Z])", part)
    if len(sub) > 1:
        return [s.strip() for s in sub if s.strip()]
    return [part]


def _parse_single_residence(part: str) -> dict | None:
    """
    Parse one location string (possibly status-annotated, possibly with sub-location paren).
    Sub-location parens are stripped (decision C): "Shells Town(153rd Branch)" → "Shells Town".
    Returns {"name", "slug", "status"} or None.
    """
    part = re.sub(r"\[\d+\]", "", part).strip()
    part = re.sub(r"≠", "", part).strip()
    part = re.sub(r"\(\s*Non-Canon\s*\)", "", part, flags=re.I).strip()
    if not part:
        return None

    paren_contents = re.findall(r"\(([^)]+)\)", part)
    status = extract_status(paren_contents)

    # Strip ALL parentheticals to get bare location name
    name = re.sub(r"\s*\([^)]*\)\s*", " ", part).strip()
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return None

    return {"name": name, "slug": slugify(name), "status": status}


def parse_residence(raw: str, char_slug: str, split_log: list) -> list[dict]:
    """
    Parse Residence field into a list of {"name", "slug", "status"}.
    Fused entries are split and appended to split_log.
    """
    raw = re.sub(r"\[\d+\]", "", raw).strip()
    if not raw:
        return []

    results = []
    for semicolon_part in raw.split(";"):
        semicolon_part = semicolon_part.strip()
        if not semicolon_part:
            continue

        sub_parts = _split_fused(semicolon_part)
        if len(sub_parts) > 1:
            split_log.append({
                "char": char_slug,
                "original": semicolon_part,
                "split_into": sub_parts,
            })

        for sp in sub_parts:
            entry = _parse_single_residence(sp)
            if entry:
                results.append(entry)

    return results


# ── Cypher ────────────────────────────────────────────────────────────────────

MERGE_LOCATION = """
MERGE (l:Location {slug: $slug})
ON CREATE SET l.name = $name
"""

MERGE_BORN_IN = """
MATCH (c:Character {opwikiID: $opwikiID})
MATCH (l:Location {slug: $slug})
MERGE (c)-[:BORN_IN]->(l)
"""

MERGE_LOCATED_IN = """
MATCH (child:Location {slug: $child_slug})
MATCH (parent:Location {slug: $parent_slug})
MERGE (child)-[:LOCATED_IN]->(parent)
"""

MERGE_RESIDES_IN = """
MATCH (c:Character {opwikiID: $opwikiID})
MATCH (l:Location {slug: $slug})
MERGE (c)-[:RESIDES_IN {status: $status}]->(l)
"""


# ── import ────────────────────────────────────────────────────────────────────

def _parse_all(records: list[dict]) -> tuple[dict, dict, dict, set, list]:
    """
    Phase 1 (pure parse, no DB). Returns:
      char_origins    — opwikiID → list of origin loc dicts
      char_residences — opwikiID → list of residence dicts
      all_locations   — slug → name
      located_in_pairs — set of (child_slug, parent_slug)
      split_log       — list of fused-entry records
    """
    char_origins: dict[str, list] = {}
    char_residences: dict[str, list] = {}
    all_locations: dict[str, str] = {}
    located_in_pairs: set[tuple] = set()
    split_log: list[dict] = []

    for record in records:
        opwiki = (record.get("source_name") or "").strip()
        if not opwiki:
            continue

        origin_raw = (record.get("Origin") or "").strip()
        if origin_raw:
            locs = parse_origin(origin_raw)
            if locs:
                char_origins[opwiki] = locs
                for loc in locs:
                    all_locations[loc["slug"]] = loc["name"]
                    if loc["parent_slug"]:
                        located_in_pairs.add((loc["slug"], loc["parent_slug"]))

        res_raw = (record.get("Residence") or "").strip()
        if res_raw:
            entries = parse_residence(res_raw, opwiki, split_log)
            if entries:
                char_residences[opwiki] = entries
                for e in entries:
                    all_locations[e["slug"]] = e["name"]

    return char_origins, char_residences, all_locations, located_in_pairs, split_log


def run_import(driver, records: list[dict], apply: bool) -> tuple[dict, list]:
    char_origins, char_residences, all_locations, located_in_pairs, split_log = _parse_all(records)

    dry_stats = {
        "location_nodes": len(all_locations),
        "born_in": sum(len(v) for v in char_origins.values()),
        "located_in": len(located_in_pairs),
        "resides_in": sum(len(v) for v in char_residences.values()),
        "skipped": 0,
    }

    if not apply:
        return dry_stats, split_log

    # Phase 2: write
    write_stats = {k: 0 for k in dry_stats}

    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT location_slug IF NOT EXISTS "
            "FOR (l:Location) REQUIRE l.slug IS UNIQUE"
        )

        # All location nodes first so relationship MATCHes succeed
        for slug, name in all_locations.items():
            try:
                session.run(MERGE_LOCATION, slug=slug, name=name)
                write_stats["location_nodes"] += 1
            except Exception as e:
                print(f"  [SKIP] location {slug!r}: {e}", file=sys.stderr)
                write_stats["skipped"] += 1

        # :BORN_IN
        for opwiki, locs in char_origins.items():
            for loc in locs:
                try:
                    session.run(MERGE_BORN_IN, opwikiID=opwiki, slug=loc["slug"])
                    write_stats["born_in"] += 1
                except Exception as e:
                    print(f"  [SKIP] {opwiki} BORN_IN {loc['slug']!r}: {e}", file=sys.stderr)
                    write_stats["skipped"] += 1

        # :LOCATED_IN
        for child_slug, parent_slug in located_in_pairs:
            try:
                session.run(MERGE_LOCATED_IN, child_slug=child_slug, parent_slug=parent_slug)
                write_stats["located_in"] += 1
            except Exception as e:
                print(f"  [SKIP] LOCATED_IN {child_slug!r}→{parent_slug!r}: {e}", file=sys.stderr)
                write_stats["skipped"] += 1

        # :RESIDES_IN
        for i, (opwiki, entries) in enumerate(char_residences.items()):
            for entry in entries:
                try:
                    session.run(MERGE_RESIDES_IN,
                                opwikiID=opwiki, slug=entry["slug"], status=entry["status"])
                    write_stats["resides_in"] += 1
                except Exception as e:
                    print(f"  [SKIP] {opwiki} RESIDES_IN {entry['slug']!r}: {e}", file=sys.stderr)
                    write_stats["skipped"] += 1

            if (i + 1) % 100 == 0:
                print(f"  RESIDES_IN: {i + 1}/{len(char_residences)} characters written...")

    return write_stats, split_log


# ── split log ─────────────────────────────────────────────────────────────────

def write_split_log(split_log: list[dict], log_path: str):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"# Residence fusion splits — {datetime.now().isoformat()[:19]}\n")
        f.write(f"# {len(split_log)} fused entries split\n\n")
        for entry in split_log:
            f.write(f"[{entry['char']}]\n")
            f.write(f"  BEFORE : {entry['original']!r}\n")
            f.write(f"  AFTER  : {entry['split_into']}\n\n")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import :Location nodes and location relationships into Neo4j."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write to Neo4j. Default is dry-run (no writes)."
    )
    args = parser.parse_args()

    data_path = os.path.join(ROOT, DATA_FILE)
    with open(data_path, encoding="utf-8") as f:
        records = json.load(f)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Loaded {len(records)} characters from {DATA_FILE}")
    print(f"Mode: {mode}")
    print()

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        stats, split_log = run_import(driver, records, apply=args.apply)
    finally:
        driver.close()

    print()
    print(f"{'=' * 50}")
    print(f"Location import [{mode}]")
    print(f"{'=' * 50}")
    print(f"  :Location nodes  : {stats['location_nodes']}")
    print(f"  :BORN_IN rels    : {stats['born_in']}")
    print(f"  :LOCATED_IN rels : {stats['located_in']}")
    print(f"  :RESIDES_IN rels : {stats['resides_in']}")
    if stats["skipped"]:
        print(f"  Skipped (errors) : {stats['skipped']}")

    print()
    if split_log:
        log_path = os.path.join(ROOT, "logs", "residence_splits.log")
        if args.apply:
            write_split_log(split_log, log_path)
            print(f"  Fused Residence entries split : {len(split_log)}")
            print(f"  Split log written to          : logs/residence_splits.log")
        else:
            print(f"  Fused Residence entries to split : {len(split_log)}")
            print(f"  [DRY-RUN] Split log would be written to logs/residence_splits.log")
    else:
        print(f"  No fused Residence entries detected.")

    if not args.apply:
        print()
        print("  No writes made. Run with --apply to commit.")


if __name__ == "__main__":
    main()
