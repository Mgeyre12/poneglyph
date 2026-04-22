"""
apply_patch.py
--------------
Applies a diff JSON (from diff_snapshots.py) to the Neo4j graph.

Behavior:
  CHANGED  → updates the specific Neo4j properties that changed
  NEW      → creates Character node + affiliations/fruit/debut (future: week 7)
  REMOVED  → marks node with removed_at timestamp (never deletes)

Safety:
  --dry-run is the DEFAULT. Pass --apply to actually write to the graph.
  Every run logs to logs/patches/YYYY-MM-DD_HH-MM.log with before/after values.

Usage:
  python apply_patch.py --dry-run diff/2026-04-21_diff.json   # preview (default)
  python apply_patch.py --apply   diff/2026-04-21_diff.json   # commit to graph
"""

import sys
import os
import json
import argparse
from datetime import datetime, date
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Mussa1234"

# Properties that live on the :Character node and map directly from raw field names.
# Fields not in this map are metadata-only (voice actors, live-action, etc.) and
# are stored as raw string properties but NOT used for graph relationships.
DIRECT_PROPS = {
    "Official English Name": "name",
    "Romanized Name": "nameRomanized",
    "Japanese Name": "nameJapanese",
    "Status": "status",
    "Age": "age",
    "Height": "height_cm",
    "Birthday": "birthday",
    "Blood Type": "bloodType",
    "Epithet": "epithet",
    "Debut": "debutChapter",
    "Origin": "origin",
}

# Fields to skip entirely (not meaningful for the graph)
SKIP_FIELDS = {"source_name", "source_url", "_meta"}


def connect():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    return driver


def setup_log(diff_path: str) -> tuple[str, list]:
    """Create log file path and return (path, log_lines list)."""
    now = datetime.now().strftime("%Y-%m-%d_%H-%M")
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "patches")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{now}.log")
    return log_path, []


def write_log(log_path: str, lines: list):
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ── CHANGED: update properties ────────────────────────────────────────────────

def apply_changed(session, entry: dict, dry_run: bool, log: list) -> int:
    slug = entry["slug"]
    updates = 0

    for fc in entry["field_changes"]:
        field = fc["field"]
        new_val = fc["new"]

        if field in SKIP_FIELDS or field not in DIRECT_PROPS:
            # Store as raw string property prefixed with raw_
            prop = f"raw_{field.replace(' ', '_').lower()}"
        else:
            prop = DIRECT_PROPS[field]

        log_line = (
            f"CHANGED | {slug} | {prop} | "
            f"{str(fc['old'])[:60]!r} -> {str(new_val)[:60]!r}"
        )
        log.append(log_line)

        if dry_run:
            print(f"  [DRY-RUN] SET {slug}.{prop} = {str(new_val)[:50]!r}")
        else:
            session.run(
                f"MATCH (c:Character {{opwikiID: $slug}}) SET c.`{prop}` = $val",
                slug=slug, val=new_val
            )
            print(f"  SET {slug}.{prop} = {str(new_val)[:50]!r}")
            updates += 1

    return updates


# ── REMOVED: mark with removed_at ────────────────────────────────────────────

def apply_removed(session, entry: dict, dry_run: bool, log: list) -> int:
    slug = entry["slug"]
    now = datetime.now().isoformat()

    log.append(f"REMOVED | {slug} | marked removed_at={now}")

    if dry_run:
        print(f"  [DRY-RUN] MARK {slug} as removed_at={now}")
        return 0
    else:
        session.run(
            "MATCH (c:Character {opwikiID: $slug}) SET c.removed_at = $ts",
            slug=slug, ts=now
        )
        print(f"  MARKED {slug} as removed_at={now}")
        return 1


# ── NEW: stub — full ingestion is week 7 ─────────────────────────────────────

def apply_new(entry: dict, dry_run: bool, log: list):
    slug = entry["slug"]
    log.append(f"NEW | {slug} | ingestion deferred to week 7")
    print(f"  [SKIPPED] {slug} — new character ingestion is week 7 work")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Apply a snapshot diff to the Neo4j graph")
    parser.add_argument("diff_file", help="Path to diff JSON from diff_snapshots.py")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="Preview changes without writing (default)")
    mode.add_argument("--apply", action="store_true",
                      help="Commit changes to the graph")
    args = parser.parse_args()

    dry_run = not args.apply

    if not os.path.exists(args.diff_file):
        sys.exit(f"Diff file not found: {args.diff_file}")

    with open(args.diff_file, encoding="utf-8") as f:
        diff = json.load(f)

    s = diff["summary"]
    log_path, log = setup_log(args.diff_file)

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    print(f"\nApply patch [{mode_label}]")
    print(f"  Source: {args.diff_file}")
    print(f"  {s['new']} new, {s['removed']} removed, {s['changed']} changed\n")

    log.append(f"Patch run: {datetime.now().isoformat()} [{mode_label}]")
    log.append(f"Source: {args.diff_file}")
    log.append(f"Summary: {s['new']} new, {s['removed']} removed, {s['changed']} changed")
    log.append("=" * 60)

    if dry_run:
        driver = None
        session = None
    else:
        driver = connect()
        session = driver.session()

    total_updates = 0
    total_removals = 0

    try:
        # NEW characters
        if diff["new"]:
            print(f"--- NEW ({len(diff['new'])}) ---")
            for entry in diff["new"]:
                apply_new(entry, dry_run, log)

        # CHANGED characters
        if diff["changed"]:
            print(f"\n--- CHANGED ({len(diff['changed'])}) ---")
            for entry in diff["changed"]:
                print(f"\n{entry['slug']}:")
                n = apply_changed(session, entry, dry_run, log)
                total_updates += n

        # REMOVED characters — only safe to apply on full snapshots
        if diff["removed"]:
            new_count = diff["summary"]["total_new"]
            old_count = diff["summary"]["total_old"]
            is_partial = new_count < old_count * 0.9
            if is_partial:
                print(
                    f"\n--- REMOVED ({len(diff['removed'])}) SKIPPED ---"
                    f"\n  Partial snapshot ({new_count}/{old_count} chars)."
                    f"\n  Run with a full snapshot to safely mark removals."
                )
                log.append(f"REMOVED: skipped — partial snapshot ({new_count}/{old_count})")
            else:
                print(f"\n--- REMOVED ({len(diff['removed'])}) ---")
                for entry in diff["removed"]:
                    n = apply_removed(session, entry, dry_run, log)
                    total_removals += n

    finally:
        if session:
            session.close()
        if driver:
            driver.close()

    log.append("=" * 60)
    log.append(f"Done. Updates applied: {total_updates}, Removals marked: {total_removals}")
    write_log(log_path, log)

    print(f"\n{'='*50}")
    if dry_run:
        print(f"DRY-RUN complete. No changes written.")
        print(f"Re-run with --apply to commit.")
    else:
        print(f"Done. {total_updates} properties updated, {total_removals} nodes marked removed.")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()
