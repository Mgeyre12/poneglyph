"""
import_affiliations.py
----------------------
Creates :Organization nodes and (:Character)-[:AFFILIATED_WITH]->(:Organization)
relationships from the Affiliations field in the character JSON.

What it does:
  - Reads data/full-character-data-processed-2.json
  - Splits the semicolon-delimited Affiliations field per character
  - Parses (annotation) suffixes — stores both raw and normalized status on the rel
  - MERGEs :Organization nodes keyed on org_id (lowercase, underscored name)
  - MERGEs :AFFILIATED_WITH relationships from existing :Character nodes
  - Is idempotent: safe to re-run
  - Logs skipped/malformed entries to logs/affiliations_skipped.log

Name normalization scheme (org_id):
  - Lowercase
  - Spaces → underscores
  - Remove all characters except [a-z0-9 _-]
  - Example: "Straw Hat Pirates" → "straw_hat_pirates"
  - Example: "Clan of D." → "clan_of_d"

Status normalization (relationship property):
  - No annotation → "current"
  - Contains "former" or "formerly" → "former"
  - Contains "defected" → "defected"
  - Contains "disbanded" → "disbanded"
  - Contains "temporary" or "temporarily" → "temporary"
  - "semi-retired" → "semi-retired"
  - "descended" → "descended"
  - Anything else → kept as-is (status_raw still always stored)

Usage:
  python import_affiliations.py
"""

import json
import os
import re
from neo4j import GraphDatabase

# ── connection ────────────────────────────────────────────────────────────────
NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "Mussa1234"

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "full-character-data-processed-2.json")
LOG_FILE  = os.path.join(os.path.dirname(__file__), "logs", "affiliations_skipped.log")

# ── helpers ───────────────────────────────────────────────────────────────────

def normalize_org_id(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]", "", s)
    s = re.sub(r" +", "_", s)
    s = s.strip("_")
    return s


def normalize_status(raw_annotation: str | None) -> str:
    if raw_annotation is None:
        return "current"
    a = raw_annotation.lower()
    if "former" in a or "formerly" in a:
        return "former"
    if "defected" in a:
        return "defected"
    if "disbanded" in a:
        return "disbanded"
    if "temporary" in a or "temporarily" in a:
        return "temporary"
    if "semi-retired" in a:
        return "semi-retired"
    if "descended" in a:
        return "descended"
    return a  # keep raw for anything else (sub-groups, roles, branches, etc.)


def parse_affiliations(raw: str) -> list[dict]:
    """
    Parse a raw Affiliations string into a list of dicts with keys:
      org_name, org_id, status, status_raw
    Returns empty list if raw is empty/None.
    """
    if not raw:
        return []

    entries = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue

        m = re.match(r"^(.*?)\(([^)]+)\)\s*$", part)
        if m:
            org_name   = m.group(1).strip()
            status_raw = m.group(2).strip()
        else:
            org_name   = part
            status_raw = None

        if not org_name:
            continue

        org_id = normalize_org_id(org_name)
        if not org_id:
            continue

        entries.append({
            "org_name":   org_name,
            "org_id":     org_id,
            "status":     normalize_status(status_raw),
            "status_raw": status_raw,
        })
    return entries


# ── import ────────────────────────────────────────────────────────────────────

MERGE_ORG_QUERY = """
MERGE (o:Organization {org_id: $org_id})
ON CREATE SET o.name = $name
"""

MERGE_REL_QUERY = """
MATCH (c:Character {opwikiID: $opwikiID})
MATCH (o:Organization {org_id: $org_id})
MERGE (c)-[r:AFFILIATED_WITH {org_id: $org_id}]->(o)
SET r.status     = $status,
    r.status_raw = $status_raw
"""


def run_import(driver, records: list[dict]) -> None:
    skipped = []
    rels_written = 0
    orgs_seen = set()
    chars_with_affiliations = 0

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT org_id IF NOT EXISTS "
            "FOR (o:Organization) REQUIRE o.org_id IS UNIQUE"
        )

        for i, record in enumerate(records):
            opwiki_id = record.get("source_name", "?")
            raw_aff   = record.get("Affiliations") or ""

            if not raw_aff.strip():
                continue

            entries = parse_affiliations(raw_aff)
            if not entries:
                skipped.append({
                    "opwikiID": opwiki_id,
                    "raw":      raw_aff,
                    "reason":   "parse returned no entries",
                })
                continue

            chars_with_affiliations += 1

            for entry in entries:
                try:
                    # MERGE the org node
                    session.run(
                        MERGE_ORG_QUERY,
                        org_id=entry["org_id"],
                        name=entry["org_name"],
                    )
                    orgs_seen.add(entry["org_id"])

                    # MERGE the relationship
                    session.run(
                        MERGE_REL_QUERY,
                        opwikiID=opwiki_id,
                        org_id=entry["org_id"],
                        status=entry["status"],
                        status_raw=entry["status_raw"],
                    )
                    rels_written += 1

                except Exception as e:
                    skipped.append({
                        "opwikiID": opwiki_id,
                        "org":      entry["org_name"],
                        "raw":      raw_aff,
                        "reason":   str(e),
                    })

            if (i + 1) % 100 == 0:
                print(f"  {i + 1} / {len(records)} characters processed...")

    print(f"\nDone.")
    print(f"  Characters with affiliations processed : {chars_with_affiliations}")
    print(f"  Unique :Organization nodes seen        : {len(orgs_seen)}")
    print(f"  :AFFILIATED_WITH relationships written : {rels_written}")
    print(f"  Skipped entries                        : {len(skipped)}")

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

    print("Importing affiliations...")
    run_import(driver, records)

    driver.close()


if __name__ == "__main__":
    main()
