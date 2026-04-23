"""
promote_pending.py
------------------
Review and promote staged characters from data/pending_review/ into the graph.

Modes:
  --list                              print all pending characters
  --promote <opwikiID>                dry-run a single promotion
  --promote <opwikiID> --apply        commit a single promotion
  --promote-all                       dry-run all pending
  --promote-all --apply               commit all pending (with confirmation prompt)
  --reject <opwikiID> --reason "..."  move to data/rejected/ (no graph change)

Dry-run is the default for any promote action. --apply is required to commit.

Logs to logs/ingestion/promotions_YYYY-MM-DD.log
"""

import sys
import os
import json
import re
import argparse
import shutil
from datetime import date, datetime
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING_DIR = os.path.join(ROOT, "data", "pending_review")
REJECTED_DIR = os.path.join(ROOT, "data", "rejected")
LOG_DIR = os.path.join(ROOT, "logs", "ingestion")

FLAGGED = {"Ragnir", "Ratatoskr", "Warrior_God"}


# ── pending file helpers ──────────────────────────────────────────────────────

def list_pending() -> list[str]:
    """Return sorted opwikiID slugs for all pending character JSONs."""
    if not os.path.isdir(PENDING_DIR):
        return []
    return sorted(
        f[:-5]
        for f in os.listdir(PENDING_DIR)
        if f.endswith(".json") and not f.startswith("REVIEW_")
    )


def load_pending(opwiki_id: str) -> dict:
    path = os.path.join(PENDING_DIR, f"{opwiki_id}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── field parsers (matches existing import_characters.py logic) ───────────────

def parse_age(raw: str | None) -> int | None:
    if not raw:
        return None
    clean = re.sub(r"\[\d+\]", "", raw)  # strip citation refs before parsing
    if re.search(r"\bunknown\b", clean, re.IGNORECASE):
        return None
    segments = [s.strip() for s in clean.split(";") if s.strip()]
    last = segments[-1]
    m = re.search(r"\d+", last)
    return int(m.group()) if m else None


def parse_height(raw: str | None) -> float | None:
    if not raw:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*cm", str(raw))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def parse_chapter_number(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.search(r"\d+", str(raw))
    return int(m.group()) if m else None


def parse_debut_chapter(raw: str | None) -> int | None:
    """
    Extract chapter number from Debut strings like:
      "Chapter 1130"
      "Chapter 107;Episode 64[1]"
      "SBS Volume 114[1]"  → None (not a chapter)
    """
    if not raw:
        return None
    m = re.search(r"[Cc]hapter\s*(\d+)", str(raw))
    return int(m.group(1)) if m else None


# ── character node props ──────────────────────────────────────────────────────

def build_node_props(record: dict) -> dict:
    """
    Build a clean props dict for a :Character node from a staged (raw scraped) record.
    Handles both processed fields (debut_chapter, height_cm) and raw scraped fields
    (Debut, Height) since staged records come directly from the scraper.
    """
    name = (
        record.get("Official English Name")
        or record.get("Romanized Name")
        or record.get("source_name")
    )

    debut_chapter = (
        parse_chapter_number(record.get("debut_chapter"))
        or parse_debut_chapter(record.get("Debut"))
    )
    height_cm = (
        _try_float(record.get("height_cm"))
        or parse_height(record.get("Height"))
    )

    props = {
        "opwikiID": record["source_name"],
        "opwikiURL": record.get("source_url"),
        "name": name,
        "nameJapanese": record.get("Japanese Name"),
        "nameRomanized": record.get("Romanized Name"),
        "status": record.get("Status"),
        "age": parse_age(record.get("Age")),
        "height_cm": height_cm,
        "bloodType": record.get("Blood Type"),
        "birthday": record.get("Birthday"),
        "epithet": record.get("Epithet"),
        "debutChapter": debut_chapter,
    }
    return {k: v for k, v in props.items() if v is not None}


def _try_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ── affiliation helpers (matches import_affiliations.py logic) ────────────────

def normalize_org_id(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]", "", s)
    s = re.sub(r" +", "_", s)
    return s.strip("_")


def normalize_status(raw: str | None) -> str:
    if raw is None:
        return "current"
    a = raw.lower()
    if "former" in a or "formerly" in a:
        return "former"
    if "defected" in a:
        return "defected"
    if "disbanded" in a:
        return "disbanded"
    if "temporary" in a or "temporarily" in a:
        return "temporary"
    return a


def parse_affiliations(raw: str) -> list[dict]:
    if not raw:
        return []
    # Strip wiki citation refs like [1], [2] before splitting
    raw = re.sub(r"\[\d+\]", "", raw)
    entries = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(.*?)\(([^)]+)\)\s*$", part)
        if m:
            org_name, status_raw = m.group(1).strip(), m.group(2).strip()
        else:
            org_name, status_raw = part, None
        if not org_name:
            continue
        org_id = normalize_org_id(org_name)
        if org_id:
            entries.append({
                "org_name": org_name,
                "org_id": org_id,
                "status": normalize_status(status_raw),
                "status_raw": status_raw,
            })
    return entries


# ── Cypher queries ────────────────────────────────────────────────────────────

MERGE_CHARACTER = """
MERGE (c:Character {opwikiID: $opwikiID})
SET c += $props
"""

MERGE_ORG = """
MERGE (o:Organization {org_id: $org_id})
ON CREATE SET o.name = $name
"""

MERGE_AFFILIATED = """
MATCH (c:Character {opwikiID: $opwikiID})
MATCH (o:Organization {org_id: $org_id})
MERGE (c)-[r:AFFILIATED_WITH {org_id: $org_id}]->(o)
SET r.status = $status, r.status_raw = $status_raw
"""

MERGE_DEBUTED_IN = """
MATCH (c:Character {opwikiID: $opwikiID})
MATCH (ch:Chapter {number: $number})
MERGE (c)-[:DEBUTED_IN]->(ch)
"""

MERGE_ATE_FRUIT = """
MATCH (c:Character {opwikiID: $opwikiID})
MATCH (f:DevilFruit)
WHERE toLower(f.name) = toLower($fruit_name)
   OR toLower(f.fruit_id) = toLower($fruit_name)
MERGE (c)-[r:ATE_FRUIT {status: "current"}]->(f)
"""


# ── dry-run preview ───────────────────────────────────────────────────────────

def preview_promotion(opwiki_id: str, record: dict) -> None:
    props = build_node_props(record)
    affs = parse_affiliations(record.get("Affiliations") or "")
    debut_ch = props.get("debutChapter")
    fruit = record.get("Devil Fruit")

    print(f"\n  Character node props:")
    for k, v in props.items():
        print(f"    {k}: {v}")

    if affs:
        print(f"\n  Affiliations ({len(affs)}):")
        for a in affs:
            print(f"    → {a['org_name']}  (status: {a['status']})")
    else:
        print(f"\n  Affiliations: none")

    if debut_ch:
        print(f"\n  DEBUTED_IN → Chapter {debut_ch}")
    else:
        print(f"\n  DEBUTED_IN → skipped (no chapter number parsed from Debut field)")

    if fruit and fruit != "—":
        print(f"\n  ATE_FRUIT → will attempt match on \"{fruit}\"")
    else:
        print(f"\n  ATE_FRUIT: none")


# ── apply promotion ───────────────────────────────────────────────────────────

def apply_promotion(driver, opwiki_id: str, record: dict) -> list[str]:
    """
    Write Character node + relationships to Neo4j.
    Returns list of log lines.
    """
    log = []
    props = build_node_props(record)
    affs = parse_affiliations(record.get("Affiliations") or "")
    debut_ch = props.get("debutChapter")
    fruit = record.get("Devil Fruit")

    with driver.session() as session:
        session.run(MERGE_CHARACTER, opwikiID=opwiki_id, props=props)
        log.append(f"CHAR  {opwiki_id}  name={props.get('name')}")

        for a in affs:
            try:
                session.run(MERGE_ORG, org_id=a["org_id"], name=a["org_name"])
                session.run(
                    MERGE_AFFILIATED,
                    opwikiID=opwiki_id,
                    org_id=a["org_id"],
                    status=a["status"],
                    status_raw=a["status_raw"],
                )
                log.append(f"AFF   {opwiki_id} → {a['org_name']} ({a['status']})")
            except Exception as e:
                log.append(f"AFF_ERR  {opwiki_id} → {a['org_name']}  {e}")

        if debut_ch:
            try:
                session.run(MERGE_DEBUTED_IN, opwikiID=opwiki_id, number=debut_ch)
                log.append(f"DEBUT {opwiki_id} → Chapter {debut_ch}")
            except Exception as e:
                log.append(f"DEBUT_ERR  {opwiki_id}  {e}")

        if fruit and fruit not in ("—", ""):
            try:
                result = session.run(
                    MERGE_ATE_FRUIT, opwikiID=opwiki_id, fruit_name=fruit
                )
                log.append(f"FRUIT {opwiki_id} → {fruit}")
            except Exception as e:
                log.append(f"FRUIT_ERR  {opwiki_id} → {fruit}  {e}")

    return log


def move_to_snapshot(opwiki_id: str, record: dict) -> str:
    """Move promoted JSON from pending_review/ to snapshots/YYYY-MM-DD/characters/."""
    today = date.today().isoformat()
    snap_dir = os.path.join(ROOT, "data", "snapshots", today, "characters")
    os.makedirs(snap_dir, exist_ok=True)

    record["_meta"]["review_status"] = "promoted"
    record["_meta"]["promoted_at"] = datetime.now().isoformat()

    dest = os.path.join(snap_dir, f"{opwiki_id}.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    src = os.path.join(PENDING_DIR, f"{opwiki_id}.json")
    os.remove(src)
    return dest


# ── reject ────────────────────────────────────────────────────────────────────

def reject_character(opwiki_id: str, reason: str) -> None:
    os.makedirs(REJECTED_DIR, exist_ok=True)
    src = os.path.join(PENDING_DIR, f"{opwiki_id}.json")

    if os.path.exists(src):
        record = load_pending(opwiki_id)
        record["_meta"]["review_status"] = "rejected"
        record["_meta"]["rejected_at"] = datetime.now().isoformat()
        record["_meta"]["rejection_reason"] = reason

        dest = os.path.join(REJECTED_DIR, f"{opwiki_id}.json")
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        os.remove(src)
        print(f"  Rejected: {opwiki_id} → data/rejected/")
        print(f"  Reason: {reason}")
    else:
        # No staged file — write a minimal rejection record
        os.makedirs(REJECTED_DIR, exist_ok=True)
        dest = os.path.join(REJECTED_DIR, f"{opwiki_id}.json")
        with open(dest, "w", encoding="utf-8") as f:
            json.dump({
                "opwikiID": opwiki_id,
                "wiki_url": f"https://onepiece.fandom.com/wiki/{opwiki_id}",
                "rejected_at": datetime.now().isoformat(),
                "rejected_by": "manual",
                "reason": reason,
                "stage": "never_staged",
            }, f, indent=2)
        print(f"  Rejection recorded (no staged file existed): {opwiki_id}")
        print(f"  Reason: {reason}")


# ── orchestration ─────────────────────────────────────────────────────────────

def cmd_list() -> None:
    pending = list_pending()
    if not pending:
        print("No pending characters.")
        return
    print(f"Pending characters ({len(pending)}):\n")
    for slug in pending:
        try:
            record = load_pending(slug)
            name = (
                record.get("Official English Name")
                or record.get("Romanized Name")
                or slug
            )
            status = record.get("Status", "—")
            debut = record.get("Debut") or record.get("debut_chapter") or "—"
            flag = "  ⚠️ FLAGGED" if slug in FLAGGED else ""
            print(f"  {slug:<35}  {name:<30}  status={status}  debut={debut}{flag}")
        except Exception as e:
            print(f"  {slug}  (could not read: {e})")


def cmd_promote(opwiki_id: str, apply: bool, driver, log_lines: list) -> bool:
    src = os.path.join(PENDING_DIR, f"{opwiki_id}.json")
    if not os.path.exists(src):
        print(f"  ERROR: {opwiki_id}.json not found in data/pending_review/")
        return False

    record = load_pending(opwiki_id)
    flag_note = "  ⚠️  FLAGGED — review carefully" if opwiki_id in FLAGGED else ""
    print(f"\n{'='*60}")
    print(f"  Promoting: {opwiki_id}{flag_note}")
    print(f"{'='*60}")

    if not apply:
        preview_promotion(opwiki_id, record)
        print(f"\n  [DRY RUN] No changes made. Pass --apply to commit.")
        return True

    print(f"  Applying...")
    written = apply_promotion(driver, opwiki_id, record)
    for line in written:
        print(f"    {line}")
        log_lines.append(line)

    dest = move_to_snapshot(opwiki_id, record)
    print(f"  Moved JSON → {dest}")
    log_lines.append(f"MOVED {opwiki_id} → {dest}")
    return True


def cmd_promote_all(apply: bool, driver, log_lines: list) -> None:
    pending = list_pending()
    if not pending:
        print("No pending characters.")
        return

    print(f"Pending: {len(pending)} characters")
    for slug in pending:
        flag = "  ⚠️ FLAGGED" if slug in FLAGGED else ""
        print(f"  {slug}{flag}")

    if apply:
        confirm = input(f"\nPromote all {len(pending)} characters? [yes/N] ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return

    for slug in pending:
        cmd_promote(slug, apply, driver, log_lines)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Review and promote staged characters into Neo4j."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all pending characters")
    group.add_argument("--promote", metavar="OPWIKI_ID", help="Promote a single character")
    group.add_argument("--promote-all", action="store_true", help="Promote all pending")
    group.add_argument("--reject", metavar="OPWIKI_ID", help="Reject a character")

    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry-run)")
    parser.add_argument("--reason", metavar="TEXT", help="Rejection reason (required with --reject)")
    args = parser.parse_args()

    today = date.today().isoformat()
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"promotions_{today}.log")
    log_lines = [
        f"# Promotions log",
        f"# Run: {datetime.now().isoformat()}",
        f"# Apply: {args.apply}",
        "",
    ]

    if args.list:
        cmd_list()
        return

    if args.reject:
        if not args.reason:
            print("ERROR: --reject requires --reason \"text\"")
            sys.exit(1)
        reject_character(args.reject, args.reason)
        log_lines.append(f"REJECT  {args.reject}  reason={args.reason}")
        with open(log_path, "a") as f:
            f.write("\n".join(log_lines) + "\n")
        return

    driver = None
    if args.apply:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        print("Connected to Neo4j.\n")

    if args.promote:
        cmd_promote(args.promote, args.apply, driver, log_lines)
    elif args.promote_all:
        cmd_promote_all(args.apply, driver, log_lines)

    if driver:
        driver.close()

    with open(log_path, "a") as f:
        f.write("\n".join(log_lines) + "\n")

    if not args.apply and (args.promote or args.promote_all):
        print(f"\nDry run complete. Pass --apply to commit.")


if __name__ == "__main__":
    main()
