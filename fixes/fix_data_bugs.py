"""
fix_data_bugs.py
----------------
Patches known data bugs identified during Week 5 stress testing.

Fixes:
  1. Luffy height_cm: 91.0 → 174.0 (upstream scraper bug)
  2. Koby: remove the Marine 153rd Branch (former) relationship —
     he's still an active Marine (SWORD); the sub-branch "former" is
     misleading and causes false positives in former-Marine queries.
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from utils.neo4j_env import get_neo4j_config

NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, _ = get_neo4j_config()


def run_fixes(driver):
    with driver.session() as session:

        # Fix 1: Luffy height
        result = session.run(
            """
            MATCH (c:Character)
            WHERE c.opwikiID = 'Monkey_D._Luffy'
            SET c.height_cm = 174.0
            RETURN c.name, c.height_cm AS new_height
            """
        )
        row = result.single()
        if row:
            print(f"[1] Luffy height set to {row['new_height']} cm ✓")
        else:
            print("[1] Luffy not found — check opwikiID")

        # Fix 2: Remove Koby's false "former" Marine sub-branch relationship
        result = session.run(
            """
            MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization)
            WHERE toLower(c.name) CONTAINS 'koby'
              AND toLower(o.name) CONTAINS 'marine'
              AND r.status IN ['former', 'defected', 'disbanded']
            DELETE r
            RETURN count(r) AS removed
            """
        )
        row = result.single()
        removed = row["removed"] if row else 0
        print(f"[2] Koby former-Marine relationships removed: {removed} ✓")


def main():
    print(f"Connecting to {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Connected.\n")
    run_fixes(driver)
    driver.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
