"""
import_arcs.py
--------------
Creates :Arc nodes and (:Chapter)-[:IN_ARC]->(:Arc) relationships.

What it does:
  - Reads data/arcs.json (33 arcs, Romance Dawn through Elbaf)
  - MERGEs one :Arc node per arc, keyed on arc_order (stable int key)
  - For every existing :Chapter node, finds which arc its number falls within
    and creates a (:Chapter)-[:IN_ARC]->(:Arc) relationship
  - Elbaf Arc uses end_chapter: 9999 as a sentinel for "ongoing" —
    any chapter >= 1126 falls into it
  - Is idempotent: safe to re-run
  - Logs Chapter nodes that don't fall inside any arc range

Usage:
  python import_arcs.py
"""

import json
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# ── connection ────────────────────────────────────────────────────────────────
load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from utils.neo4j_env import get_neo4j_config

NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, _ = get_neo4j_config()

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "arcs.json")
LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "arcs_skipped.log")

# ── helpers ───────────────────────────────────────────────────────────────────


def find_arc(chapter_number: int, arcs: list[dict]) -> dict | None:
    for arc in arcs:
        if arc["start_chapter"] <= chapter_number <= arc["end_chapter"]:
            return arc
    return None


# ── import ────────────────────────────────────────────────────────────────────

MERGE_ARC_QUERY = """
MERGE (a:Arc {arc_order: $arc_order})
SET a.name          = $name,
    a.saga          = $saga,
    a.start_chapter = $start_chapter,
    a.end_chapter   = $end_chapter
"""

MERGE_IN_ARC_QUERY = """
MATCH (ch:Chapter {number: $number})
MATCH (a:Arc {arc_order: $arc_order})
MERGE (ch)-[:IN_ARC]->(a)
"""


def run_import(driver, arcs: list[dict]) -> None:
    skipped = []
    arcs_written = 0
    rels_written = 0

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT arc_order IF NOT EXISTS "
            "FOR (a:Arc) REQUIRE a.arc_order IS UNIQUE"
        )

        # Write all Arc nodes first
        for arc in arcs:
            session.run(
                MERGE_ARC_QUERY,
                arc_order=arc["arc_order"],
                name=arc["name"],
                saga=arc["saga"],
                start_chapter=arc["start_chapter"],
                end_chapter=arc["end_chapter"],
            )
            arcs_written += 1

        print(f"  {arcs_written} :Arc nodes written.")

        # Fetch all existing Chapter numbers
        result = session.run(
            "MATCH (ch:Chapter) RETURN ch.number AS number ORDER BY ch.number"
        )
        chapter_numbers = [r["number"] for r in result]

        print(f"  Linking {len(chapter_numbers)} :Chapter nodes to arcs...")

        for number in chapter_numbers:
            arc = find_arc(number, arcs)
            if arc is None:
                skipped.append(
                    {"chapter": number, "reason": "no arc range covers this chapter"}
                )
                continue
            session.run(MERGE_IN_ARC_QUERY, number=number, arc_order=arc["arc_order"])
            rels_written += 1

    print(f"\nDone.")
    print(f"  :Arc nodes written       : {arcs_written}")
    print(f"  :IN_ARC rels written     : {rels_written}")
    print(f"  Chapters with no arc     : {len(skipped)}")

    if skipped:
        with open(LOG_FILE, "w") as f:
            for entry in skipped:
                f.write(json.dumps(entry) + "\n")
        print(f"  Skipped log: {LOG_FILE}")


# ── main ──────────────────────────────────────────────────────────────────────


def main():
    print(f"Reading {DATA_FILE}...")
    with open(DATA_FILE) as f:
        arcs = json.load(f)
    print(f"Loaded {len(arcs)} arc definitions.\n")

    print(f"Connecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Connected.\n")

    print("Importing arcs...")
    run_import(driver, arcs)

    driver.close()


if __name__ == "__main__":
    main()
