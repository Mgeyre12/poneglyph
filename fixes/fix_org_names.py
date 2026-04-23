"""
fix_org_names.py
----------------
Repairs 31 malformed :Organization nodes caused by scraper artifacts in the
source data. Two types of fixes:

  1. Simple rename — one malformed org → one correctly-named org.
     If the target org already exists (e.g. 'Marines'), existing character
     relationships are redirected to it. The malformed node is deleted.

  2. Split — one malformed org that is really 2-3 orgs concatenated
     (e.g. 'Kid PiratesNinja-Pirate-Mink-Samurai Alliance').
     Each character affiliated with the phantom node gets new relationships
     to each of the component orgs. The phantom node is deleted.

In both cases the org_id on the target node is (re-)computed from the
canonical name using the same normalization as import_affiliations.py.

Is idempotent: safe to re-run.

Usage:
  python fix_org_names.py
"""

import re
import os
import json
from neo4j import GraphDatabase
from dotenv import load_dotenv

# ── connection ────────────────────────────────────────────────────────────────
load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from utils.neo4j_env import get_neo4j_config

NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, _ = get_neo4j_config()

LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "org_fix.log")

# ── fix table ─────────────────────────────────────────────────────────────────
# key   = current malformed org name (must match exactly what's in Neo4j)
# value = list of canonical target names
#   - len == 1 → simple rename / merge into existing
#   - len >  1 → split: each character gets a relationship to each target

FIXES = {
    # ── missing space (simple rename) ─────────────────────────────────────────
    "ArabastaKingdom": ["Arabasta Kingdom"],
    "KingNeptune": ["King Neptune"],
    "World GovernmentOrphanage": ["World Government Orphanage"],
    "FujinandRaijin": ["Fujin and Raijin"],
    "Whitebeard Pirates2nd Division": ["Whitebeard Pirates 2nd Division"],
    "Marine16th Branch": ["Marine 16th Branch"],
    "MarineG-5": ["Marine G-5"],
    "MarinesG-1 Branch": ["Marines G-1 Branch"],
    "MarinesPhotography Department": ["Marines Photography Department"],
    "G-2Base": ["G-2 Base"],
    "G-5Unit 01": ["G-5 Unit 01"],
    # ── missing space after "the" ──────────────────────────────────────────────
    "Ally of theBig Mom Pirates": ["Ally of the Big Mom Pirates"],
    "Ally of theFlying Pirates": ["Ally of the Flying Pirates"],
    "Ally of theNew Fish-Man Pirates": ["Ally of the New Fish-Man Pirates"],
    "Ally of theWhitebeard Pirates": ["Ally of the Whitebeard Pirates"],
    "Animals of theIsland of Rare Animals": ["Animals of the Island of Rare Animals"],
    "Subordinate of theWhitebeard Pirates": ["Subordinate of the Whitebeard Pirates"],
    "Subordinates of theWhitebeard Pirates": ["Subordinates of the Whitebeard Pirates"],
    # ── trailing junk / incomplete parens ────────────────────────────────────
    "Buggy's Delivery(Unknown status)?": ["Buggy's Delivery"],
    "Marines(Headquarters": ["Marines"],
    # ── double / triple fusions (split) ──────────────────────────────────────
    "Beautiful PiratesStraw Hat Grand Fleet": [
        "Beautiful Pirates",
        "Straw Hat Grand Fleet",
    ],
    "Inuarashi Musketeer SquadNinja-Pirate-Mink-Samurai Alliance": [
        "Inuarashi Musketeer Squad",
        "Ninja-Pirate-Mink-Samurai Alliance",
    ],
    "Kid PiratesNinja-Pirate-Mink-Samurai Alliance": [
        "Kid Pirates",
        "Ninja-Pirate-Mink-Samurai Alliance",
    ],
    "Tonta CorpsStraw Hat Grand Fleet": ["Tonta Corps", "Straw Hat Grand Fleet"],
    "Tontatta KingdomScouting Unit": ["Tontatta Kingdom", "Scouting Unit"],
    "Tontatta KingdomScouting UnitStraw Hat Grand Fleet": [
        "Tontatta Kingdom",
        "Scouting Unit",
        "Straw Hat Grand Fleet",
    ],
    "Tontatta KingdomTontatta PiratesStraw Hat Grand Fleet": [
        "Tontatta Kingdom",
        "Tontatta Pirates",
        "Straw Hat Grand Fleet",
    ],
    "Tontatta PiratesStraw Hat Grand Fleet": [
        "Tontatta Pirates",
        "Straw Hat Grand Fleet",
    ],
    "Tontatta TribeScouting Unit": ["Tontatta Tribe", "Scouting Unit"],
    # ── complex Marines (split) ───────────────────────────────────────────────
    "Marines(SWORD), Marine153rd Branch": ["Marines", "Marine 153rd Branch"],
    "Marines, Marine77th Branch": ["Marines", "Marine 77th Branch"],
}

# ── helpers ───────────────────────────────────────────────────────────────────


def normalize_org_id(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]", "", s)
    s = re.sub(r" +", "_", s)
    return s.strip("_")


# ── fix logic ─────────────────────────────────────────────────────────────────


def fix_org(session, old_name: str, target_names: list[str], log: list) -> int:
    """
    Rewire all characters from old_name to each target in target_names,
    then delete the malformed org node.
    Returns number of relationships migrated.
    """
    # Find all characters + relationship metadata linked to the malformed org
    result = session.run(
        """
        MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization {name: $old_name})
        RETURN c.opwikiID AS opwikiID, r.status AS status, r.status_raw AS status_raw
    """,
        old_name=old_name,
    )
    affiliations = result.data()

    if not affiliations:
        log.append(
            {"action": "skip", "old": old_name, "reason": "no characters linked"}
        )
        return 0

    rels_written = 0

    for target_name in target_names:
        target_id = normalize_org_id(target_name)

        # Ensure the target org node exists
        session.run(
            """
            MERGE (o:Organization {org_id: $org_id})
            ON CREATE SET o.name = $name
        """,
            org_id=target_id,
            name=target_name,
        )

        # Migrate each character relationship
        for aff in affiliations:
            session.run(
                """
                MATCH (c:Character {opwikiID: $opwikiID})
                MATCH (o:Organization {org_id: $org_id})
                MERGE (c)-[r:AFFILIATED_WITH {org_id: $org_id}]->(o)
                SET r.status     = $status,
                    r.status_raw = $status_raw
            """,
                opwikiID=aff["opwikiID"],
                org_id=target_id,
                status=aff["status"],
                status_raw=aff["status_raw"],
            )
            rels_written += 1
            log.append(
                {
                    "action": "migrated",
                    "char": aff["opwikiID"],
                    "from": old_name,
                    "to": target_name,
                }
            )

    # Delete old relationships and old node
    session.run(
        """
        MATCH (o:Organization {name: $old_name})
        DETACH DELETE o
    """,
        old_name=old_name,
    )

    return rels_written


# ── main ──────────────────────────────────────────────────────────────────────


def run_fixes(driver) -> None:
    total_rels = 0
    total_nodes_fixed = 0
    log = []

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    with driver.session() as session:
        for old_name, target_names in FIXES.items():
            rels = fix_org(session, old_name, target_names, log)
            if rels > 0:
                total_rels += rels
                total_nodes_fixed += 1
                action = (
                    "renamed"
                    if len(target_names) == 1
                    else f"split into {len(target_names)}"
                )
                print(f"  [{action}] {old_name!r} → {target_names}")

    print(f"\nDone.")
    print(f"  Malformed org nodes fixed      : {total_nodes_fixed}")
    print(f"  Relationships migrated/created : {total_rels}")

    with open(LOG_FILE, "w") as f:
        for entry in log:
            f.write(json.dumps(entry) + "\n")
    print(f"  Full log: {LOG_FILE}")


def main():
    print(f"Connecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Connected.\n")

    print("Fixing malformed org names...")
    run_fixes(driver)

    driver.close()


if __name__ == "__main__":
    main()
