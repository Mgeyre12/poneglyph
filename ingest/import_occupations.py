"""
import_occupations.py
---------------------
Imports :Occupation nodes and :HAS_OCCUPATION relationships
from the full character dataset.

Source field: Occupations (semicolon-delimited, paren-annotated)

Parsing rules:
  "Pirate Captain"           → HAS_OCCUPATION Pirate Captain {status:"current"}
  "Bounty Hunter(former)"    → HAS_OCCUPATION Bounty Hunter {status:"former"}
  "PirateOfficer"            → camelCase split → HAS_OCCUPATION Pirate Officer (logged)
  "Rōnin(temporary)"         → HAS_OCCUPATION Rōnin {status:"temporary"}
  entries with ≠ or Non-Canon paren → skipped

CamelCase splits are logged to logs/occupation_splits.log for post-import review.

Usage:
  python import_occupations.py           # dry-run (no Neo4j writes)
  python import_occupations.py --apply   # write to Neo4j
"""

import json
import re
import os
import sys
import argparse
from datetime import datetime
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "Mussa1234"
DATA_FILE = "data/full-character-data-processed-2.json"

ROOT = os.path.dirname(os.path.abspath(__file__))


# ── helpers ───────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"['''`]", "", s)
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


# ── Occupations parsing ───────────────────────────────────────────────────────

def parse_occupations(raw: str, char_slug: str, split_log: list) -> list[dict]:
    """
    Returns list of {"name", "slug", "status"}.
    CamelCase-split entries are appended to split_log as {"char", "before", "after"}.
    Non-canon entries (≠ or explicit Non-Canon paren) are skipped entirely.
    """
    raw = re.sub(r"\[\d+\]", "", raw).strip()
    if not raw:
        return []

    results = []
    for part in raw.split(";"):
        part = part.strip().strip(",")
        if not part:
            continue

        # Skip non-canon entries
        if "≠" in part:
            continue
        paren_contents = re.findall(r"\(([^)]+)\)", part)
        if any("non-canon" in p.lower() for p in paren_contents):
            continue

        status = extract_status(paren_contents)

        # Strip ALL parentheticals to get bare occupation name
        name = re.sub(r"\s*\([^)]*\)\s*", " ", part).strip()
        name = re.sub(r"≠", "", name).strip()
        name = re.sub(r"\s+", " ", name).strip().strip(",;")
        if not name:
            continue

        # Apply camelCase split
        split_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
        split_name = re.sub(r"\s+", " ", split_name).strip()

        if split_name != name:
            split_log.append({
                "char": char_slug,
                "before": name,
                "after": split_name,
            })

        results.append({
            "name": split_name,
            "slug": slugify(split_name),
            "status": status,
        })

    return results


# ── Cypher ────────────────────────────────────────────────────────────────────

MERGE_OCCUPATION = """
MERGE (o:Occupation {slug: $slug})
ON CREATE SET o.name = $name
"""

MERGE_HAS_OCCUPATION = """
MATCH (c:Character {opwikiID: $opwikiID})
MATCH (o:Occupation {slug: $slug})
MERGE (c)-[:HAS_OCCUPATION {status: $status}]->(o)
"""


# ── import ────────────────────────────────────────────────────────────────────

def _parse_all(records: list[dict]) -> tuple[dict, dict, list]:
    """
    Phase 1 (pure parse, no DB).
    Returns:
      char_occupations — opwikiID → list of occupation dicts
      all_occupations  — slug → name
      split_log        — list of camelCase split records
    """
    char_occupations: dict[str, list] = {}
    all_occupations: dict[str, str] = {}
    split_log: list[dict] = []

    for record in records:
        opwiki = (record.get("source_name") or "").strip()
        if not opwiki:
            continue

        occ_raw = (record.get("Occupations") or "").strip()
        if not occ_raw:
            continue

        entries = parse_occupations(occ_raw, opwiki, split_log)
        if entries:
            char_occupations[opwiki] = entries
            for e in entries:
                all_occupations[e["slug"]] = e["name"]

    return char_occupations, all_occupations, split_log


def run_import(driver, records: list[dict], apply: bool) -> tuple[dict, list]:
    char_occupations, all_occupations, split_log = _parse_all(records)

    dry_stats = {
        "occupation_nodes": len(all_occupations),
        "has_occupation": sum(len(v) for v in char_occupations.values()),
        "skipped": 0,
    }

    if not apply:
        return dry_stats, split_log

    write_stats = {k: 0 for k in dry_stats}

    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT occupation_slug IF NOT EXISTS "
            "FOR (o:Occupation) REQUIRE o.slug IS UNIQUE"
        )

        # Create all occupation nodes first
        for slug, name in all_occupations.items():
            try:
                session.run(MERGE_OCCUPATION, slug=slug, name=name)
                write_stats["occupation_nodes"] += 1
            except Exception as e:
                print(f"  [SKIP] occupation {slug!r}: {e}", file=sys.stderr)
                write_stats["skipped"] += 1

        # :HAS_OCCUPATION relationships
        for i, (opwiki, entries) in enumerate(char_occupations.items()):
            for entry in entries:
                try:
                    session.run(
                        MERGE_HAS_OCCUPATION,
                        opwikiID=opwiki, slug=entry["slug"], status=entry["status"]
                    )
                    write_stats["has_occupation"] += 1
                except Exception as e:
                    print(f"  [SKIP] {opwiki} HAS_OCCUPATION {entry['slug']!r}: {e}", file=sys.stderr)
                    write_stats["skipped"] += 1

            if (i + 1) % 200 == 0:
                print(f"  HAS_OCCUPATION: {i + 1}/{len(char_occupations)} characters written...")

    return write_stats, split_log


# ── split log ─────────────────────────────────────────────────────────────────

def write_split_log(split_log: list[dict], log_path: str):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"# Occupation camelCase splits — {datetime.now().isoformat()[:19]}\n")
        f.write(f"# {len(split_log)} entries split\n\n")
        for entry in split_log:
            f.write(f"[{entry['char']}]\n")
            f.write(f"  BEFORE : {entry['before']!r}\n")
            f.write(f"  AFTER  : {entry['after']!r}\n\n")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import :Occupation nodes and :HAS_OCCUPATION relationships into Neo4j."
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
    print(f"Occupation import [{mode}]")
    print(f"{'=' * 50}")
    print(f"  :Occupation nodes  : {stats['occupation_nodes']}")
    print(f"  :HAS_OCCUPATION    : {stats['has_occupation']}")
    if stats["skipped"]:
        print(f"  Skipped (errors)   : {stats['skipped']}")

    print()
    log_path = os.path.join(ROOT, "logs", "occupation_splits.log")
    if split_log:
        if args.apply:
            write_split_log(split_log, log_path)
            print(f"  CamelCase entries split : {len(split_log)}")
            print(f"  Split log written to    : logs/occupation_splits.log")
        else:
            print(f"  CamelCase entries to split : {len(split_log)}")
            print(f"  [DRY-RUN] Split log would be written to logs/occupation_splits.log")
    else:
        print(f"  No camelCase splits needed.")

    if not args.apply:
        print()
        print("  No writes made. Run with --apply to commit.")


if __name__ == "__main__":
    main()
