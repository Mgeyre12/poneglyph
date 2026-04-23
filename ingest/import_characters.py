"""
import_characters.py
--------------------
Loads One Piece characters from the processed JSON file into a local Neo4j
database as :Character nodes.

What it does:
  - Reads data/full-character-data-processed-2.json (1,517 records)
  - MERGEs one :Character node per record, keyed on `opwikiID`
  - Maps scalar fields only (no relationships today)
  - Is idempotent: safe to re-run, will update existing nodes

Usage:
  pip install neo4j
  python import_characters.py

Expects NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD set in the environment
or in a .env file at the project root.
"""

import json
import re
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# ── connection ────────────────────────────────────────────────────────────────
load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from utils.neo4j_env import get_neo4j_config

NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, _ = get_neo4j_config()

DATA_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "full-character-data-processed-2.json"
)

# ── helpers ───────────────────────────────────────────────────────────────────


def parse_age(raw: str | None) -> int | None:
    """Extract the most recent age from strings like '7 (debut);17 (pre-timeskip);19 (post-timeskip)'."""
    if not raw:
        return None
    # Take the last semicolon-separated segment, grab the first number in it
    segments = [s.strip() for s in raw.split(";") if s.strip()]
    last = segments[-1]
    match = re.search(r"\d+", last)
    return int(match.group()) if match else None


def parse_height(raw: str | None) -> float | None:
    """Convert height string to float cm. Returns None if unparseable."""
    if not raw:
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return None


def parse_debut_chapter(raw: str | None) -> int | None:
    """Convert 'Chapter 1' → 1. Returns None if missing or unparseable."""
    if not raw:
        return None
    match = re.search(r"\d+", str(raw))
    return int(match.group()) if match else None


def build_node_props(record: dict) -> dict:
    """
    Pull scalar fields from a raw JSON record and return a clean dict
    ready to write to Neo4j. List-valued fields (Affiliations, Occupations,
    voice actors) are intentionally skipped — those become relationships later.
    """
    # Prefer Official English Name; fall back to Romanized Name
    name = (
        record.get("Official English Name")
        or record.get("Romanized Name")
        or record.get("source_name")
    )

    return {
        "opwikiID": record["source_name"],  # stable unique key
        "opwikiURL": record.get("source_url"),
        "name": name,
        "nameJapanese": record.get("Japanese Name"),
        "nameRomanized": record.get("Romanized Name"),
        "status": record.get("Status"),
        "age": parse_age(record.get("Age")),
        "height_cm": parse_height(record.get("height_cm")),
        "bloodType": record.get("Blood Type"),
        "birthday": record.get("Birthday"),
        "epithet": record.get("Epithet"),
        "debutChapter": parse_debut_chapter(record.get("debut_chapter")),
        "debutEpisode": parse_debut_chapter(record.get("debut_episode")),
    }


# ── import ────────────────────────────────────────────────────────────────────

MERGE_QUERY = """
MERGE (c:Character {opwikiID: $opwikiID})
SET c += $props
"""


def run_import(driver, records: list[dict]) -> None:
    failed = []
    loaded = 0

    with driver.session() as session:
        # Create a uniqueness constraint so MERGE is fast and IDs stay unique.
        # Safe to run even if the constraint already exists (IF NOT EXISTS).
        session.run(
            "CREATE CONSTRAINT character_id IF NOT EXISTS "
            "FOR (c:Character) REQUIRE c.opwikiID IS UNIQUE"
        )

        for i, record in enumerate(records):
            try:
                props = build_node_props(record)
                # Strip None values — no point storing null properties
                props_clean = {k: v for k, v in props.items() if v is not None}
                session.run(
                    MERGE_QUERY, opwikiID=props_clean["opwikiID"], props=props_clean
                )
                loaded += 1
            except Exception as e:
                failed.append(
                    {"source_name": record.get("source_name", "?"), "error": str(e)}
                )

            if (i + 1) % 100 == 0:
                print(f"  {i + 1} / {len(records)} processed...")

    print(f"\nDone. {loaded} nodes written, {len(failed)} failed.")
    if failed:
        print("Failed records:")
        for f in failed:
            print(f"  {f['source_name']}: {f['error']}")


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

    print("Importing characters...")
    run_import(driver, records)

    driver.close()


if __name__ == "__main__":
    main()
