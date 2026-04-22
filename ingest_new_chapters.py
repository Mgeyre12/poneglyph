"""
ingest_new_chapters.py
----------------------
Ingests new :Chapter nodes (and their :IN_ARC relationships) into Neo4j.
Detects the gap automatically from the graph vs. wiki, or accepts an explicit
list via --chapters.

Usage:
  python ingest_new_chapters.py              # dry-run, auto-detect gap
  python ingest_new_chapters.py --apply      # commit to graph
  python ingest_new_chapters.py --chapters 1163 1164  # specific chapters, dry-run
  python ingest_new_chapters.py --chapters 1163 1164 --apply
"""

import sys
import os
import json
import re
import argparse
import requests
from datetime import date, datetime
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Mussa1234"

ARCS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "arcs.json")
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "ingestion")

FANDOM_API = "https://onepiece.fandom.com/api.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── arc helpers ───────────────────────────────────────────────────────────────

def load_arcs(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def find_arc(chapter_num: int, arcs: list[dict]) -> dict | None:
    for arc in arcs:
        if arc["start_chapter"] <= chapter_num <= arc["end_chapter"]:
            return arc
    return None


# ── wiki helpers ──────────────────────────────────────────────────────────────

def _chapter_exists(http: requests.Session, number: int) -> bool:
    resp = http.get(
        FANDOM_API,
        params={"action": "query", "titles": f"Chapter_{number}",
                "prop": "info", "format": "json"},
        headers=HEADERS, timeout=10,
    )
    pages = resp.json().get("query", {}).get("pages", {})
    return all("missing" not in p for p in pages.values())


def get_wiki_max_chapter(http: requests.Session, graph_max: int) -> int:
    hi = graph_max + 50
    while _chapter_exists(http, hi):
        hi += 50
    lo = graph_max
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if _chapter_exists(http, mid):
            lo = mid
        else:
            hi = mid
    return lo


def fetch_chapter_title(http: requests.Session, number: int) -> str | None:
    """
    Fetch the English chapter title from the wiki infobox wikitext.
    Returns None if not found or on any error.
    """
    try:
        resp = http.get(
            FANDOM_API,
            params={
                "action": "parse",
                "page": f"Chapter_{number}",
                "prop": "wikitext",
                "section": "0",
                "format": "json",
            },
            headers=HEADERS,
            timeout=10,
        )
        wikitext = resp.json().get("parse", {}).get("wikitext", {}).get("*", "")
        m = re.search(r"\|\s*ename\s*=\s*([^\n|{}]+)", wikitext, re.IGNORECASE)
        if not m:
            m = re.search(r"\|\s*title\s*=\s*([^\n|{}]+)", wikitext, re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            title = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", title)
            title = re.sub(r"<[^>]+>", "", title).strip()
            return title or None
    except Exception:
        pass
    return None


# ── Neo4j helpers ─────────────────────────────────────────────────────────────

def get_graph_max_chapter(driver) -> int:
    with driver.session() as session:
        result = session.run(
            "MATCH (ch:Chapter) RETURN max(ch.number) AS mx"
        ).single()
        return result["mx"] or 0


MERGE_CHAPTER = """
MERGE (ch:Chapter {number: $number})
ON CREATE SET ch.title = $title
"""

MERGE_IN_ARC = """
MATCH (ch:Chapter {number: $number})
MATCH (a:Arc {name: $arc_name})
MERGE (ch)-[:IN_ARC]->(a)
"""


# ── dry-run preview ───────────────────────────────────────────────────────────

def dry_run(chapters: list[dict], arcs: list[dict]) -> None:
    print("\n[DRY RUN] Chapters that would be written:\n")
    print(f"  {'#':>6}  {'Arc':<30}  Title")
    print(f"  {'-'*6}  {'-'*30}  {'-'*35}")
    unmatched = []
    for ch in chapters:
        arc = find_arc(ch["number"], arcs)
        arc_name = arc["name"] if arc else "⚠ NO ARC FOUND"
        title = ch.get("title") or "(no title fetched)"
        print(f"  {ch['number']:>6}  {arc_name:<30}  {title}")
        if not arc:
            unmatched.append(ch["number"])
    print(f"\n  Total: {len(chapters)} chapters")
    if unmatched:
        print(f"  WARNING: {len(unmatched)} chapters have no arc match: {unmatched}")
    print("\nDry run complete — no changes made. Pass --apply to commit.")


# ── apply ─────────────────────────────────────────────────────────────────────

def apply(driver, chapters: list[dict], arcs: list[dict], log_path: str) -> None:
    log_lines = [
        f"# Chapter ingestion log",
        f"# Run: {datetime.now().isoformat()}",
        f"# Mode: --apply",
        f"# Chapters: {len(chapters)}",
        "",
    ]
    success = 0
    errors = []

    with driver.session() as session:
        for ch in chapters:
            num = ch["number"]
            title = ch.get("title")
            arc = find_arc(num, arcs)

            if not arc:
                msg = f"Chapter {num}: no arc match — skipped"
                print(f"  WARNING: {msg}")
                errors.append(msg)
                log_lines.append(f"SKIP  ch={num}  reason=no_arc_match")
                continue

            try:
                session.run(MERGE_CHAPTER, number=num, title=title)
                session.run(MERGE_IN_ARC, number=num, arc_name=arc["name"])
                success += 1
                print(f"  [OK] Chapter {num} → {arc['name']}  \"{title or ''}\"")
                log_lines.append(
                    f"OK    ch={num}  arc={arc['name']}  title={title}"
                )
            except Exception as e:
                msg = f"Chapter {num}: {e}"
                errors.append(msg)
                log_lines.append(f"ERR   ch={num}  {e}")
                print(f"  [ERR] {msg}")

    print(f"\nDone. {success} ingested, {len(errors)} errors.")

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w") as f:
        f.write("\n".join(log_lines) + "\n")
    print(f"Log written: {log_path}")

    if errors:
        sys.exit(1)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest new :Chapter nodes into Neo4j."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Commit changes to graph (default: dry-run)"
    )
    parser.add_argument(
        "--chapters", nargs="+", type=int,
        help="Explicit chapter numbers (default: auto-detect gap vs. wiki)"
    )
    args = parser.parse_args()

    arcs = load_arcs(ARCS_FILE)
    print(f"Loaded {len(arcs)} arcs from {ARCS_FILE}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Connected to Neo4j.\n")

    if args.chapters:
        chapter_nums = sorted(set(args.chapters))
        print(f"Using provided chapters: {chapter_nums[0]}–{chapter_nums[-1]} ({len(chapter_nums)} total)")
    else:
        print("Auto-detecting chapter gap...")
        graph_max = get_graph_max_chapter(driver)
        print(f"  Graph max chapter : {graph_max}")
        http_probe = requests.Session()
        wiki_max = get_wiki_max_chapter(http_probe, graph_max)
        print(f"  Wiki max chapter  : {wiki_max}")
        if wiki_max <= graph_max:
            print("Graph is already up to date. Nothing to ingest.")
            driver.close()
            return
        chapter_nums = list(range(graph_max + 1, wiki_max + 1))
        print(f"  Gap               : {len(chapter_nums)} chapters ({chapter_nums[0]}–{chapter_nums[-1]})\n")

    # Fetch titles
    print(f"Fetching chapter titles from wiki ({len(chapter_nums)} chapters)...")
    http = requests.Session()
    chapters = []
    for num in chapter_nums:
        title = fetch_chapter_title(http, num)
        chapters.append({"number": num, "title": title})
        label = f"\"{title}\"" if title else "(no title)"
        print(f"  {num}: {label}")

    today = date.today().isoformat()
    log_path = os.path.join(LOG_DIR, f"chapters_{today}.log")

    if args.apply:
        print(f"\nApplying {len(chapters)} chapters to graph...")
        apply(driver, chapters, arcs, log_path)
    else:
        dry_run(chapters, arcs)

    driver.close()


if __name__ == "__main__":
    main()
