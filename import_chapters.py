"""
import_chapters.py
------------------
Creates :Chapter nodes and (:Character)-[:DEBUTED_IN]->(:Chapter) relationships
from the debut_chapter field on existing :Character nodes.

What it does:
  - Reads data/full-character-data-processed-2.json
  - Collects every unique debut_chapter number across all characters
  - MERGEs one :Chapter node per unique chapter number, keyed on `number` (int)
  - MERGEs :DEBUTED_IN relationships from existing :Character nodes
  - Keeps the existing scalar `debutChapter` property on :Character untouched
  - Is idempotent: safe to re-run
  - Logs characters with missing or unparseable debut_chapter to
    logs/chapters_skipped.log

Usage:
  python import_chapters.py
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
LOG_FILE  = os.path.join(os.path.dirname(__file__), "..", "logs", "chapters_skipped.log")

# ── helpers ───────────────────────────────────────────────────────────────────

def parse_chapter_number(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.search(r"\d+", str(raw))
    return int(m.group()) if m else None


# ── import ────────────────────────────────────────────────────────────────────

MERGE_CHAPTER_QUERY = """
MERGE (ch:Chapter {number: $number})
"""

MERGE_DEBUTED_QUERY = """
MATCH (c:Character {opwikiID: $opwikiID})
MATCH (ch:Chapter {number: $number})
MERGE (c)-[:DEBUTED_IN]->(ch)
"""


def run_import(driver, records: list[dict]) -> None:
    skipped = []
    chapters_seen = set()
    rels_written = 0

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT chapter_number IF NOT EXISTS "
            "FOR (ch:Chapter) REQUIRE ch.number IS UNIQUE"
        )

        for i, record in enumerate(records):
            opwiki_id = record.get("source_name", "?")
            chapter_num = parse_chapter_number(record.get("debut_chapter"))

            if chapter_num is None:
                skipped.append({
                    "opwikiID": opwiki_id,
                    "raw": record.get("debut_chapter"),
                    "reason": "missing or unparseable debut_chapter",
                })
                continue

            try:
                session.run(MERGE_CHAPTER_QUERY, number=chapter_num)
                chapters_seen.add(chapter_num)

                session.run(MERGE_DEBUTED_QUERY, opwikiID=opwiki_id, number=chapter_num)
                rels_written += 1
            except Exception as e:
                skipped.append({
                    "opwikiID": opwiki_id,
                    "chapter": chapter_num,
                    "reason": str(e),
                })

            if (i + 1) % 100 == 0:
                print(f"  {i + 1} / {len(records)} characters processed...")

    print(f"\nDone.")
    print(f"  Unique :Chapter nodes created  : {len(chapters_seen)}")
    print(f"  :DEBUTED_IN rels written       : {rels_written}")
    print(f"  Skipped (no debut_chapter)     : {len(skipped)}")

    if skipped:
        with open(LOG_FILE, "w") as f:
            for entry in skipped:
                f.write(json.dumps(entry) + "\n")
        print(f"  Skipped log written to: {LOG_FILE}")


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

    print("Importing chapters...")
    run_import(driver, records)

    driver.close()


if __name__ == "__main__":
    main()
