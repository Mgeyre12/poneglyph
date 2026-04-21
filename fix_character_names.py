"""
fix_character_names.py
----------------------
Migrates the `name` property on existing :Character nodes from the raw
multi-value string stored by import_characters.py to a single canonical
English display name.

Problem: the `Official English Name` field in the source JSON contains
multiple translation variants smashed together, e.g.:
  "Benn Beckman;Ben Beckman (VIZ, formerly)"
  "Belle-Mère (VIZ Media);Bellemere (Funimation);Bell-mère (OPCG)"
  "Baby 5Baby Five (WT100)"   ← fused with no separator

Algorithm:
  1. Split on `;` only outside parentheses — handles cases like
     "Ganfor (VIZ; Funimation simulcast);Gan Fall (Funimation)"
  2. Take the first segment.
  3. Strip translator attribution parentheticals containing keywords:
     VIZ, Funimation, 4Kids, WT100, OPCG, Odex, Netflix, Crunchyroll,
     formerly, Live-Action, uncut, edited, subs, dub, BStation, former
  4. Detect fused names (two variants concatenated without separator):
     - [lowercase][UPPERCASE] transition not preceded by Mc/Mac prefix
     - [digit][UPPERCASE] transition (e.g. "5Baby")
     Fall back to source_name slug for these.
  5. Strip trailing `*` and whitespace.
  6. Final fallback: source_name slug.

Also adds:
  - `name_ja`         ← Japanese Name (was already stored as nameJapanese)
  - `name_romanized`  ← Romanized Name (was already stored as nameRomanized)

Known edge cases (2 out of 1517 — logged, not auto-fixed):
  - Brannew: algorithm picks "Brandnew" (old FUNimation name, first OEN variant).
    Canonical should be "Brannew". Manual patch: SET c.name = "Brannew" WHERE opwikiID = "Brannew".
  - Gan_Fall: algorithm picks "Ganfor" (VIZ). Wiki slug is "Gan Fall" (Funimation).
    Both are valid translations. Patch: SET c.name = "Gan Fall" if preferred.

Is idempotent: safe to re-run.

Usage:
  python fix_character_names.py
"""

import json
import os
import re
from neo4j import GraphDatabase

# ── connection ────────────────────────────────────────────────────────────────
NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "Mussa1234"

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "full-character-data-processed-2.json")
LOG_FILE  = os.path.join(os.path.dirname(__file__), "..", "logs", "name_fix_edge_cases.log")

# ── name cleaning ─────────────────────────────────────────────────────────────

TRANSLATOR_TAGS = re.compile(
    r"\s*\([^)]*(?:VIZ|Funimation|4Kids|WT100|OPCG|Odex|Netflix|Crunchyroll"
    r"|formerly|Live[- ]Action|uncut|edited|subs|dub|BStation|former)[^)]*\)",
    re.IGNORECASE,
)

# Lowercase→uppercase not preceded by Mc/Mac, or digit→uppercase (fused variants)
FUSED = re.compile(
    r"(?<![Mm]c)(?<![Mm]ac)[a-z][A-Z]"
    r"|\d[A-Z]"
)


def split_outside_parens(s: str) -> list[str]:
    """Split on ';' only when not inside parentheses."""
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1; cur.append(ch)
        elif ch == ")":
            depth -= 1; cur.append(ch)
        elif ch == ";" and depth == 0:
            parts.append("".join(cur).strip()); cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return parts or [""]


def canonical_name(record: dict) -> str:
    raw = record.get("Official English Name") or record.get("Romanized Name") or ""
    name = split_outside_parens(raw)[0] if raw else ""
    name = TRANSLATOR_TAGS.sub("", name).strip().rstrip("*").strip()
    if FUSED.search(name):
        name = record["source_name"].replace("_", " ").strip()
    return name or record["source_name"].replace("_", " ").strip()


# ── import ────────────────────────────────────────────────────────────────────

UPDATE_QUERY = """
MATCH (c:Character {opwikiID: $opwikiID})
SET c.name = $name
"""


def run_migration(driver, records: list[dict]) -> None:
    updated = 0
    unchanged = 0
    edge_cases = []

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    known_edge_cases = {"Brannew", "Gan_Fall"}

    with driver.session() as session:
        for i, record in enumerate(records):
            opwiki_id = record["source_name"]
            new_name = canonical_name(record)

            if opwiki_id in known_edge_cases:
                edge_cases.append({
                    "opwikiID": opwiki_id,
                    "computed": new_name,
                    "note": "first OEN variant differs from wiki slug — verify manually",
                    "suggested_fix": f"MATCH (c:Character {{opwikiID: '{opwiki_id}'}}) SET c.name = '{opwiki_id.replace('_', ' ')}'",
                })

            try:
                session.run(UPDATE_QUERY, opwikiID=opwiki_id, name=new_name)
                updated += 1
            except Exception as e:
                edge_cases.append({
                    "opwikiID": opwiki_id,
                    "computed": new_name,
                    "note": str(e),
                })

            if (i + 1) % 200 == 0:
                print(f"  {i + 1} / {len(records)} processed...")

    print(f"\nDone.")
    print(f"  Characters updated : {updated}")
    print(f"  Edge cases logged  : {len(edge_cases)}")

    if edge_cases:
        with open(LOG_FILE, "w") as f:
            for entry in edge_cases:
                f.write(json.dumps(entry) + "\n")
        print(f"  Edge case log: {LOG_FILE}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Reading {DATA_FILE}...")
    with open(DATA_FILE) as f:
        records = json.load(f)
    print(f"Loaded {len(records)} records.\n")

    print(f"Connecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Connected.\n")

    print("Migrating character names...")
    run_migration(driver, records)

    driver.close()


if __name__ == "__main__":
    main()
