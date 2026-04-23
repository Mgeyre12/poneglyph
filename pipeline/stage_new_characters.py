"""
stage_new_characters.py
-----------------------
Scrapes new characters detected by detect_new_content.py and writes them to
data/pending_review/ for human review before graph ingestion.

Does NOT touch the graph — staging only.

Output:
  data/pending_review/{opwikiID}.json   — one file per character
  data/pending_review/REVIEW_YYYY-MM-DD.md  — human-readable review doc
  logs/ingestion/staging_YYYY-MM-DD.log

Usage:
  python stage_new_characters.py                      # auto-detect new chars
  python stage_new_characters.py --slugs Foo Bar_Baz  # specific slugs
"""

import sys
import os
import json
import re
import argparse
import hashlib
import requests
import time
from datetime import date, datetime
from bs4 import BeautifulSoup
from urllib.parse import unquote
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from utils.neo4j_env import get_neo4j_config

NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, _ = get_neo4j_config()

FANDOM_API = "https://onepiece.fandom.com/api.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

PENDING_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pending_review"
)
LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "ingestion"
)

# Characters that warrant extra scrutiny in the review doc.
FLAGGED = {"Ragnir", "Ratatoskr", "Warrior_God"}


# ── Kareem's scraper loader ───────────────────────────────────────────────────

def _find_scraper_src() -> str:
    base = os.path.expanduser("~/Desktop/one_piece")
    for root, _, files in os.walk(base):
        if "onepiece_scraper.py" in files:
            return root
    raise FileNotFoundError(
        "Could not find onepiece_scraper.py under ~/Desktop/one_piece."
    )


def load_scraper():
    src = _find_scraper_src()
    if src not in sys.path:
        sys.path.insert(0, src)
    from onepiece_scraper import OnePieceScraper
    return OnePieceScraper()


# ── character detection (same logic as detect_new_content.py) ────────────────

def get_graph_char_ids(driver) -> set[str]:
    with driver.session() as session:
        return {
            r["id"]
            for r in session.run("MATCH (c:Character) RETURN c.opwikiID AS id")
            if r["id"]
        }


def get_wiki_char_slugs(http: requests.Session) -> list[str]:
    resp = http.get(
        FANDOM_API,
        params={"action": "parse", "page": "List_of_Canon_Characters",
                "prop": "text", "format": "json", "disablelimitreport": 1},
        headers=HEADERS, timeout=30,
    )
    resp.raise_for_status()
    html = resp.json().get("parse", {}).get("text", {}).get("*", "")
    soup = BeautifulSoup(html, "lxml")
    content = soup.find("div", class_="mw-parser-output")
    if not content:
        return []
    table = content.find("table", class_="sortable")
    if not table:
        return []
    slugs = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) >= 2:
            link = cells[1].find("a", href=True)
            if link:
                href = link.get("href", "")
                if href.startswith("/wiki/"):
                    slug = unquote(href.replace("/wiki/", "")).replace(" ", "_")
                    if ":" not in slug and slug not in slugs:
                        slugs.append(slug)
    return slugs


def detect_new_slugs(driver, http: requests.Session) -> list[str]:
    print("Fetching graph character IDs...")
    graph_ids = get_graph_char_ids(driver)
    print(f"  {len(graph_ids)} characters in graph")

    print("Fetching wiki character list...")
    wiki_slugs = get_wiki_char_slugs(http)
    print(f"  {len(wiki_slugs)} characters on wiki")

    new = [s for s in wiki_slugs if s not in graph_ids]
    print(f"  {len(new)} new characters detected")
    return new


# ── scraping ──────────────────────────────────────────────────────────────────

def scrape_character(scraper, http: requests.Session, slug: str) -> dict | None:
    """
    Fetch character data via MediaWiki API (action=parse&prop=text),
    parse HTML with Kareem's extract_character_data. Returns raw record or None.
    """
    resp = http.get(
        FANDOM_API,
        params={"action": "parse", "page": slug, "prop": "text",
                "format": "json", "disablelimitreport": 1},
        headers=HEADERS, timeout=30,
    )
    resp.raise_for_status()
    html = resp.json().get("parse", {}).get("text", {}).get("*", "")
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    return scraper.extract_character_data(soup, slug)


def content_hash(record: dict) -> str:
    content = {k: v for k, v in record.items() if k != "_meta"}
    serialized = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()


def add_meta(record: dict, slug: str) -> dict:
    wiki_url = record.get("source_url", f"https://onepiece.fandom.com/wiki/{slug}")
    return {
        "_meta": {
            "scraped_at": datetime.now().isoformat(),
            "wiki_url": wiki_url,
            "content_hash": content_hash(record),
            "staged_at": datetime.now().isoformat(),
            "review_status": "pending",
        },
        **record,
    }


# ── review doc ────────────────────────────────────────────────────────────────

def _field(record: dict, *keys: str) -> str:
    for k in keys:
        v = record.get(k)
        if v:
            return str(v).strip()
    return "—"


def build_review_doc(staged: list[dict], today: str) -> str:
    lines = [
        f"# Character Staging Review",
        f"",
        f"**Date:** {today}  ",
        f"**Characters staged:** {len(staged)}  ",
        f"**Pending review in:** `data/pending_review/`",
        f"",
        f"To promote a character:  `python promote_pending.py --promote <opwikiID> --apply`  ",
        f"To reject:              `python promote_pending.py --reject <opwikiID> --reason \"text\"`",
        f"",
        f"---",
        f"",
    ]

    for entry in staged:
        slug = entry["slug"]
        record = entry["record"]
        warnings = entry["warnings"]
        flag = slug in FLAGGED

        name = _field(record, "Official English Name", "Romanized Name", "source_name")
        wiki_url = record.get("source_url", f"https://onepiece.fandom.com/wiki/{slug}")
        status = _field(record, "Status")
        debut = _field(record, "Debut")
        affiliations_raw = _field(record, "Affiliations")
        affiliations = "; ".join(affiliations_raw.split(";")[:3]) if affiliations_raw != "—" else "—"
        fruit = _field(record, "Devil Fruit")
        field_count = len([k for k in record if not k.startswith("_") and k not in ("source_name", "source_url")])

        header = f"## {name}"
        if flag:
            header += "  ⚠️ FLAGGED FOR CLOSE REVIEW"
        lines.append(header)
        lines.append("")
        lines.append(f"- **opwikiID:** `{slug}`")
        lines.append(f"- **Wiki:** {wiki_url}")
        lines.append(f"- **Status:** {status}")
        lines.append(f"- **Debut:** {debut}")
        lines.append(f"- **Affiliations:** {affiliations}")
        lines.append(f"- **Devil Fruit:** {fruit}")
        lines.append(f"- **Fields scraped:** {field_count}")

        if warnings:
            lines.append(f"- **⚠️ Parse warnings:**")
            for w in warnings:
                lines.append(f"  - {w}")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Stage new characters from wiki into data/pending_review/."
    )
    parser.add_argument(
        "--slugs", nargs="+",
        help="Explicit wiki slugs (default: auto-detect vs. graph)"
    )
    parser.add_argument(
        "--delay", type=int, default=2,
        help="Seconds between wiki requests (default: 2)"
    )
    args = parser.parse_args()

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Connected to Neo4j.\n")

    http = requests.Session()

    if args.slugs:
        slugs = args.slugs
        print(f"Using provided slugs: {slugs}")
    else:
        slugs = detect_new_slugs(driver, http)

    driver.close()

    if not slugs:
        print("No new characters to stage.")
        return

    print(f"\nLoading scraper...")
    scraper = load_scraper()

    os.makedirs(PENDING_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    today = date.today().isoformat()
    log_path = os.path.join(LOG_DIR, f"staging_{today}.log")
    log_lines = [
        f"# Character staging log",
        f"# Run: {datetime.now().isoformat()}",
        f"# Slugs: {len(slugs)}",
        "",
    ]

    staged = []
    failures = []

    print(f"\nScraping {len(slugs)} characters...\n")
    for i, slug in enumerate(slugs, 1):
        flag_marker = " [FLAGGED]" if slug in FLAGGED else ""
        print(f"[{i}/{len(slugs)}] {slug}{flag_marker}")
        try:
            raw = scrape_character(scraper, http, slug)
            if not raw:
                raise ValueError("no infobox found")

            warnings = []
            field_count = len([k for k in raw if not k.startswith("_") and k not in ("source_name", "source_url")])
            if field_count < 3:
                warnings.append(f"Only {field_count} fields scraped — infobox may be sparse")
            if not raw.get("Status"):
                warnings.append("No Status field")
            if not raw.get("Debut"):
                warnings.append("No Debut field")

            record = add_meta(raw, slug)
            out_path = os.path.join(PENDING_DIR, f"{slug}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)

            staged.append({"slug": slug, "record": raw, "warnings": warnings, "path": out_path})
            log_lines.append(f"OK    slug={slug}  fields={field_count}  warnings={len(warnings)}")
            print(f"  OK ({field_count} fields){' — ' + str(len(warnings)) + ' warning(s)' if warnings else ''}")

        except Exception as e:
            failures.append({"slug": slug, "reason": str(e)})
            log_lines.append(f"FAIL  slug={slug}  reason={e}")
            print(f"  FAIL — {e}")

        if i < len(slugs):
            time.sleep(args.delay)

    # Review doc
    review_path = os.path.join(PENDING_DIR, f"REVIEW_{today}.md")
    review_md = build_review_doc(staged, today)
    with open(review_path, "w", encoding="utf-8") as f:
        f.write(review_md)

    # Log
    log_lines += ["", f"# Summary", f"Staged: {len(staged)}", f"Failed: {len(failures)}"]
    if failures:
        for f_entry in failures:
            log_lines.append(f"  FAIL: {f_entry['slug']} — {f_entry['reason']}")
    with open(log_path, "w") as f:
        f.write("\n".join(log_lines) + "\n")

    print(f"\n{'='*60}")
    print(f"Staged  : {len(staged)}")
    print(f"Failed  : {len(failures)}")
    print(f"Review  : {review_path}")
    print(f"Log     : {log_path}")

    if failures:
        print(f"\nFailed slugs:")
        for fe in failures:
            print(f"  {fe['slug']}: {fe['reason']}")


if __name__ == "__main__":
    main()
