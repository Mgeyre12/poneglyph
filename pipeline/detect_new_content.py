"""
detect_new_content.py
---------------------
Detects new chapters and characters on the wiki that aren't in the graph yet.
Detection only — does NOT ingest anything. Ingestion is week 7.

Output:
  reports/pending_updates_YYYY-MM-DD.md

Usage:
  python detect_new_content.py
"""

import sys
import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime
from urllib.parse import unquote
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

FANDOM_API = "https://onepiece.fandom.com/api.php"


# ── Neo4j queries ─────────────────────────────────────────────────────────────

def get_graph_stats(driver) -> dict:
    with driver.session() as session:
        max_ch = session.run(
            "MATCH (ch:Chapter) RETURN max(ch.number) AS max_chapter"
        ).single()["max_chapter"]

        char_ids = {
            r["id"]
            for r in session.run("MATCH (c:Character) RETURN c.opwikiID AS id")
            if r["id"]
        }

    return {"max_chapter": max_ch, "character_ids": char_ids}


# ── Chapter detection ─────────────────────────────────────────────────────────

def _chapter_exists(session: requests.Session, number: int) -> bool:
    """Return True if Chapter {number} has a wiki page."""
    resp = session.get(
        FANDOM_API,
        params={"action": "query", "titles": f"Chapter_{number}",
                "prop": "info", "format": "json"},
        headers=HEADERS, timeout=10,
    )
    pages = resp.json().get("query", {}).get("pages", {})
    return all("missing" not in p for p in pages.values())


def get_latest_wiki_chapter(session: requests.Session, graph_max: int) -> int | None:
    """
    Binary search for the highest existing chapter page on the wiki.
    Starts from graph_max and walks forward to find the ceiling.
    """
    print("Detecting latest chapter via binary search...")
    try:
        # First find an upper bound by doubling
        hi = graph_max + 50
        while _chapter_exists(session, hi):
            hi += 50

        # Binary search between graph_max and hi
        lo = graph_max
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if _chapter_exists(session, mid):
                lo = mid
            else:
                hi = mid

        print(f"  Latest chapter: {lo}")
        return lo

    except Exception as e:
        print(f"  Warning: chapter detection failed — {e}")
        return None


# ── Character detection ───────────────────────────────────────────────────────

def get_wiki_character_slugs(session: requests.Session) -> list[str]:
    """
    Fetch the full canon character list from the wiki via API parse.
    Uses action=parse&prop=text to avoid 403 on direct page requests.
    Returns list of wiki slug strings.
    """
    print("Fetching canon character list from wiki...")
    try:
        resp = session.get(
            FANDOM_API,
            params={"action": "parse", "page": "List_of_Canon_Characters",
                    "prop": "text", "format": "json", "disablelimitreport": 1},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        html = resp.json().get("parse", {}).get("text", {}).get("*", "")
        soup = BeautifulSoup(html, "lxml")

        content = soup.find("div", class_="mw-parser-output")
        if not content:
            print("  Warning: could not find page content")
            return []

        table = content.find("table", class_="sortable")
        if not table:
            print("  Warning: could not find character table")
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

        print(f"  Found {len(slugs)} characters on wiki")
        return slugs

    except Exception as e:
        print(f"  Warning: character list fetch failed — {e}")
        return []


# ── Load known-missing set ────────────────────────────────────────────────────

def load_known_missing() -> set[str]:
    """Load the audit/missing_characters.md baseline — empty since Week 6 found 0."""
    return set()


# ── Report ────────────────────────────────────────────────────────────────────

def render_report(
    graph_max_ch: int,
    wiki_latest_ch: int | None,
    new_chars: list[str],
    wiki_total: int,
    graph_total: int,
) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Pending Updates Report",
        f"",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"## Chapters",
        f"",
    ]

    if wiki_latest_ch:
        gap = wiki_latest_ch - graph_max_ch
        lines += [
            f"| | |",
            f"|---|---|",
            f"| Graph latest chapter | {graph_max_ch} |",
            f"| Wiki latest chapter | {wiki_latest_ch} |",
            f"| Gap | **{gap} chapters** |",
            f"",
        ]
        if gap > 0:
            lines.append(
                f"The graph is {gap} chapter(s) behind the wiki. "
                f"New chapters may contain new characters or arc changes."
            )
        else:
            lines.append("Graph is up to date with the wiki.")
    else:
        lines.append(f"- Graph latest: Chapter {graph_max_ch}")
        lines.append("- Wiki latest: *could not fetch*")

    lines += [
        f"",
        f"## Characters",
        f"",
        f"| | |",
        f"|---|---|",
        f"| Characters in graph | {graph_total} |",
        f"| Characters on wiki | {wiki_total or 'fetch failed'} |",
        f"| New on wiki (not in graph) | **{len(new_chars)}** |",
        f"",
    ]

    if new_chars:
        lines.append("### New characters detected")
        lines.append("")
        for slug in new_chars:
            url = f"https://onepiece.fandom.com/wiki/{slug}"
            lines.append(f"- [{slug}]({url})")
    else:
        lines.append("No new characters detected.")

    lines += [
        f"",
        f"---",
        f"",
        f"*Detection only. To ingest new content, run the Week 7 ingestion pipeline.*",
    ]

    return "\n".join(lines)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to Neo4j...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Connected.\n")

    graph = get_graph_stats(driver)
    driver.close()

    graph_max_ch = graph["max_chapter"]
    graph_char_ids = graph["character_ids"]
    print(f"Graph: {len(graph_char_ids)} characters, latest chapter {graph_max_ch}\n")

    http = requests.Session()

    wiki_latest_ch = get_latest_wiki_chapter(http, graph_max_ch)
    if wiki_latest_ch:
        print(f"Wiki latest chapter: {wiki_latest_ch}")
    print()

    wiki_slugs = get_wiki_character_slugs(http)
    known_missing = load_known_missing()

    new_chars = [
        s for s in wiki_slugs
        if s not in graph_char_ids and s not in known_missing
    ]
    print(f"\nNew characters not in graph: {len(new_chars)}")
    if new_chars:
        for s in new_chars[:10]:
            print(f"  {s}")
        if len(new_chars) > 10:
            print(f"  ... and {len(new_chars) - 10} more")

    report = render_report(
        graph_max_ch=graph_max_ch,
        wiki_latest_ch=wiki_latest_ch,
        new_chars=new_chars,
        wiki_total=len(wiki_slugs),
        graph_total=len(graph_char_ids),
    )

    today = date.today().isoformat()
    os.makedirs("reports", exist_ok=True)
    report_path = f"reports/pending_updates_{today}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nReport written: {report_path}")


if __name__ == "__main__":
    main()
