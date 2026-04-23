"""
import_devil_fruits.py
----------------------
Creates :DevilFruit nodes and (:Character)-[:ATE_FRUIT]->(:DevilFruit)
relationships from data/devil_fruits.json.

What it does:
  - Reads data/devil_fruits.json (134 records under top-level key "characters")
  - MERGEs :DevilFruit nodes keyed on fruit_id (source_name slug)
  - Resolves Current User / Previous User names to existing :Character nodes
    by trying Official English Name first, then source_name slug conversion
  - Creates [:ATE_FRUIT {status: "current"|"former"}] relationships
  - Multi-user fields (semicolon-separated) are split and each token matched
    individually — Seraphim copies (e.g. "S-Snake") are not in the character
    dataset and will be logged, not silently skipped
  - Is idempotent: safe to re-run
  - Logs unresolved / skipped entries to logs/fruit_user_skipped.log

Relationship model for fruits with multiple users:
  (:Character)-[:ATE_FRUIT {status: "former"}]->(:DevilFruit)  # Previous User
  (:Character)-[:ATE_FRUIT {status: "current"}]->(:DevilFruit) # Current User
  Query "who has ever eaten this fruit?" with no status filter.
  Filter on status: "current" when you want the living wielder.

Usage:
  python import_devil_fruits.py
"""

import json
import os
import re
from neo4j import GraphDatabase
from dotenv import load_dotenv

# ── connection ────────────────────────────────────────────────────────────────
load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from utils.neo4j_env import get_neo4j_config

NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, _ = get_neo4j_config()

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "devil_fruits.json")
LOG_FILE = os.path.join(
    os.path.dirname(__file__), "..", "logs", "fruit_user_skipped.log"
)

# ── helpers ───────────────────────────────────────────────────────────────────


def parse_debut_chapter(raw: str | None) -> int | None:
    """Extract first chapter number from strings like 'Chapter 1; Episode 4'."""
    if not raw:
        return None
    m = re.search(r"[Cc]hapter\s*(\d+)", str(raw))
    return int(m.group(1)) if m else None


def build_fruit_props(record: dict) -> dict:
    # Official English Name may contain multiple translations separated by ";".
    # Use the first one as the canonical display name.
    raw_name = (
        record.get("Official English Name")
        or record.get("Romanized Name")
        or record["source_name"]
    )
    name = raw_name.split(";")[0].strip()

    props = {
        "fruit_id": record["source_name"],
        "name": name,
        "japanese_name": record.get("Japanese Name"),
        "type": record.get("Type"),
        "meaning": record.get("Meaning"),
        "debut_chapter": parse_debut_chapter(
            record.get("Usage Debut") or record.get("Fruit Debut")
        ),
    }
    return {k: v for k, v in props.items() if v is not None}


def build_char_lookup(chars: list[dict]) -> dict[str, str]:
    """
    Returns a dict mapping every known name variant → opwikiID (source_name).
    Tries: Official English Name, slug-to-spaces conversion of source_name.
    """
    lookup = {}
    for c in chars:
        opwiki_id = c["source_name"]
        oen = c.get("Official English Name")
        if oen:
            lookup[oen.strip()] = opwiki_id
        # slug → spaced name (e.g. "Marshall_D._Teach" → "Marshall D. Teach")
        spaced = opwiki_id.replace("_", " ")
        lookup[spaced] = opwiki_id
    return lookup


def resolve_user(raw_name: str, lookup: dict[str, str]) -> str | None:
    """Return opwikiID for a character name, or None if not found."""
    name = raw_name.strip()
    if name in lookup:
        return lookup[name]
    # Try stripping trailing parenthetical (e.g. "S-Snake (Artificial)")
    stripped = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
    return lookup.get(stripped)


# ── import ────────────────────────────────────────────────────────────────────

MERGE_FRUIT_QUERY = """
MERGE (f:DevilFruit {fruit_id: $fruit_id})
SET f += $props
"""

MERGE_ATE_QUERY = """
MATCH (c:Character {opwikiID: $opwikiID})
MATCH (f:DevilFruit {fruit_id: $fruit_id})
MERGE (c)-[r:ATE_FRUIT {fruit_id: $fruit_id, status: $status}]->(f)
"""


def process_user_field(
    raw: str | None,
    status: str,
    fruit_id: str,
    lookup: dict[str, str],
    session,
    skipped: list,
) -> int:
    """Parse a user field, resolve names, write relationships. Returns rel count."""
    if not raw:
        return 0
    written = 0
    tokens = [t.strip() for t in raw.split(";") if t.strip()]
    for token in tokens:
        opwiki_id = resolve_user(token, lookup)
        if opwiki_id is None:
            skipped.append(
                {
                    "fruit_id": fruit_id,
                    "user_field": status,
                    "raw_value": token,
                    "reason": "character not found in dataset",
                }
            )
            continue
        try:
            session.run(
                MERGE_ATE_QUERY,
                opwikiID=opwiki_id,
                fruit_id=fruit_id,
                status=status,
            )
            written += 1
        except Exception as e:
            skipped.append(
                {
                    "fruit_id": fruit_id,
                    "user_field": status,
                    "raw_value": token,
                    "reason": str(e),
                }
            )
    return written


def run_import(driver, fruits: list[dict], chars: list[dict]) -> None:
    skipped = []
    fruits_written = 0
    rels_written = 0

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    lookup = build_char_lookup(chars)

    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT fruit_id IF NOT EXISTS "
            "FOR (f:DevilFruit) REQUIRE f.fruit_id IS UNIQUE"
        )

        for i, record in enumerate(fruits):
            fruit_id = record["source_name"]
            try:
                props = build_fruit_props(record)
                session.run(MERGE_FRUIT_QUERY, fruit_id=fruit_id, props=props)
                fruits_written += 1
            except Exception as e:
                skipped.append(
                    {"fruit_id": fruit_id, "reason": f"node write failed: {e}"}
                )
                continue

            rels_written += process_user_field(
                record.get("Current User"),
                "current",
                fruit_id,
                lookup,
                session,
                skipped,
            )
            rels_written += process_user_field(
                record.get("Previous User"),
                "former",
                fruit_id,
                lookup,
                session,
                skipped,
            )

            if (i + 1) % 25 == 0:
                print(f"  {i + 1} / {len(fruits)} fruits processed...")

    print(f"\nDone.")
    print(f"  :DevilFruit nodes written  : {fruits_written}")
    print(f"  :ATE_FRUIT rels written    : {rels_written}")
    print(f"  Skipped / unresolved       : {len(skipped)}")

    if skipped:
        with open(LOG_FILE, "w") as f:
            for entry in skipped:
                f.write(json.dumps(entry) + "\n")
        print(f"  Skipped log written to: {LOG_FILE}")


# ── main ──────────────────────────────────────────────────────────────────────


def main():
    print(f"Reading {DATA_FILE}...")
    with open(DATA_FILE) as f:
        raw = json.load(f)
    fruits = raw["characters"]
    print(f"Loaded {len(fruits)} devil fruit records.\n")

    char_file = os.path.join(
        os.path.dirname(__file__), "data", "full-character-data-processed-2.json"
    )
    print(f"Reading character data for name lookup...")
    with open(char_file) as f:
        chars = json.load(f)
    print(f"Loaded {len(chars)} characters.\n")

    print(f"Connecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Connected.\n")

    print("Importing devil fruits...")
    run_import(driver, fruits, chars)

    driver.close()


if __name__ == "__main__":
    main()
