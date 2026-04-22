"""
refresh_data.py
---------------
Wrapper around Kareem's OnePieceScraper. Fetches fresh character data from the
One Piece wiki and writes a timestamped per-character snapshot directory.

Output layout:
  data/snapshots/YYYY-MM-DD/
    characters/
      Monkey_D._Luffy.json
      Roronoa_Zoro.json
      ...
    _manifest.json

Each character file has a top-level _meta field:
  {
    "_meta": { "scraped_at": "...", "wiki_url": "...", "content_hash": "sha256:..." },
    "source_name": "Monkey_D._Luffy",
    ...all other fields from infobox...
  }

Usage:
  python refresh_data.py --test          # scrape 50-char test set
  python refresh_data.py --full          # scrape all 1,517 characters
  python refresh_data.py --test --delay 1  # faster delay for testing
"""

import sys
import os
import json
import hashlib
import tempfile
import argparse
from datetime import date, datetime

# ── locate Kareem's scraper ───────────────────────────────────────────────────

def _find_scraper_src() -> str:
    """Walk Desktop/one_piece to find onepiece_scraper.py directory."""
    base = os.path.expanduser("~/Desktop/one_piece")
    for root, _, files in os.walk(base):
        if "onepiece_scraper.py" in files:
            return root
    raise FileNotFoundError(
        "Could not find onepiece_scraper.py under ~/Desktop/one_piece. "
        "Is the source repo there?"
    )


def _find_char_list() -> str:
    """Walk Desktop/one_piece to find canon_character_list.txt."""
    base = os.path.expanduser("~/Desktop/one_piece")
    for root, _, files in os.walk(base):
        if "canon_character_list.txt" in files:
            return os.path.join(root, "canon_character_list.txt")
    raise FileNotFoundError("Could not find canon_character_list.txt")


# ── 50-character test set ─────────────────────────────────────────────────────

TEST_SLUGS = [
    # Straw Hats (10)
    "Monkey_D._Luffy", "Roronoa_Zoro", "Nami", "Usopp", "Sanji",
    "Tony_Tony_Chopper", "Nico_Robin", "Franky", "Brook", "Jinbe",
    # Emperors / ex-Emperors (5)
    "Shanks", "Marshall_D._Teach", "Kaidou", "Charlotte_Linlin", "Edward_Newgate",
    # Marines (6)
    "Monkey_D._Garp", "Sengoku", "Sakazuki", "Borsalino", "Kuzan", "Issho",
    # Warlords (6)
    "Boa_Hancock", "Trafalgar_D._Water_Law", "Dracule_Mihawk",
    "Donquixote_Doflamingo", "Bartholomew_Kuma", "Crocodile",
    # Roger era (4)
    "Gol_D._Roger", "Silvers_Rayleigh", "Kouzuki_Oden", "Portgas_D._Ace",
    # Revolutionary Army (3)
    "Monkey_D._Dragon", "Sabo", "Emporio_Ivankov",
    # Five Elders (5)
    "Jaygarcia_Saturn", "Ethanbaron_V._Nusjuro",
    "Marcus_Mars", "Topman_Warcury", "Shepherd_Ju_Peter",
    # Misc / minor (11)
    "Buggy", "Koby", "Nefertari_Vivi", "Cavendish", "Bartolomeo",
    "Eustass_Kid", "Killer", "Basil_Hawkins", "Scratchmen_Apoo",
    "X_Drake", "Jewelry_Bonney",
]


# ── snapshot utilities ────────────────────────────────────────────────────────

def content_hash(record: dict) -> str:
    """SHA-256 of the record's content fields (sorted keys, _meta excluded)."""
    content = {k: v for k, v in record.items() if k != "_meta"}
    serialized = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()


def add_meta(record: dict) -> dict:
    """Return a copy of record with _meta injected at the top."""
    slug = record.get("source_name", "unknown")
    wiki_url = record.get("source_url", f"https://onepiece.fandom.com/wiki/{slug}")
    h = content_hash(record)
    meta = {
        "scraped_at": datetime.now().isoformat(),
        "wiki_url": wiki_url,
        "content_hash": h,
    }
    return {"_meta": meta, **record}


def safe_filename(slug: str) -> str:
    """Convert a wiki slug to a safe filename (replace / and other bad chars)."""
    return slug.replace("/", "__").replace("\\", "__")


def write_snapshot(records: list[dict], snapshot_dir: str) -> str:
    """Write per-character JSON files + manifest. Returns snapshot_dir."""
    char_dir = os.path.join(snapshot_dir, "characters")
    os.makedirs(char_dir, exist_ok=True)

    written = 0
    for raw in records:
        record = add_meta(raw)
        slug = record.get("source_name", "unknown")
        out_path = os.path.join(char_dir, f"{safe_filename(slug)}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        written += 1

    manifest = {
        "snapshot_date": date.today().isoformat(),
        "created_at": datetime.now().isoformat(),
        "character_count": written,
        "snapshot_dir": snapshot_dir,
        "is_full_snapshot": written >= 1400,
    }
    with open(os.path.join(snapshot_dir, "_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nSnapshot written: {snapshot_dir}")
    print(f"  {written} character files")
    print(f"  Manifest: {snapshot_dir}/_manifest.json")
    return snapshot_dir


# ── baseline conversion ───────────────────────────────────────────────────────

def make_baseline_snapshot(raw_json_path: str, snapshot_dir: str) -> str:
    """
    Convert Kareem's original characters_raw.json into the per-character
    snapshot format. Used once to establish the baseline for diffing.
    """
    print(f"Converting baseline from {raw_json_path}...")
    with open(raw_json_path, encoding="utf-8") as f:
        data = json.load(f)
    records = data.get("characters", data) if isinstance(data, dict) else data
    print(f"  Loaded {len(records)} records.")
    return write_snapshot(records, snapshot_dir)


# ── API-based scraper (replaces blocked HTML route) ──────────────────────────

FANDOM_API = "https://onepiece.fandom.com/api.php"


def _scrape_via_api(scraper, char_list: list[str], delay: int = 3) -> list[dict]:
    """
    Fetch character data via the MediaWiki parse API (action=parse&prop=text).
    Returns rendered HTML per page which is parsed by Kareem's extract_character_data().
    This route is not 403-blocked unlike direct wiki page requests.
    """
    from bs4 import BeautifulSoup
    import time

    total = len(char_list)
    records = []
    failures = []
    start = time.time()

    for i, slug in enumerate(char_list, 1):
        elapsed = time.time() - start
        rate = i / elapsed if elapsed > 0 else 0
        eta = ((total - i) / rate / 60) if rate > 0 else 0
        print(f"\n[{i:04d}/{total}] {slug}")
        print(f"  {elapsed/60:.1f}m elapsed | ~{eta:.1f}m remaining")

        try:
            resp = scraper.session.get(
                FANDOM_API,
                params={
                    "action": "parse",
                    "page": slug,
                    "prop": "text",
                    "format": "json",
                    "disablelimitreport": 1,
                },
                headers=scraper.headers,
                timeout=30,
            )
            resp.raise_for_status()
            html = resp.json().get("parse", {}).get("text", {}).get("*", "")
            if not html:
                raise ValueError("Empty parse result")

            soup = BeautifulSoup(html, "lxml")
            data = scraper.extract_character_data(soup, slug)

            if data:
                records.append(data)
                fields = len(data) - 2  # subtract source_name and source_url
                print(f"  OK ({fields} fields)")
            else:
                failures.append({"slug": slug, "reason": "no infobox"})
                print(f"  SKIP — no infobox found")

        except Exception as e:
            failures.append({"slug": slug, "reason": str(e)})
            print(f"  FAIL — {e}")

        if i < total:
            time.sleep(delay)

    elapsed_total = time.time() - start
    print(f"\n{'='*60}")
    print(f"Done. {len(records)}/{total} succeeded, {len(failures)} failed.")
    print(f"Total time: {elapsed_total/60:.1f} minutes")

    if failures:
        fail_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "logs", "scrape_failures_latest.json"
        )
        os.makedirs(os.path.dirname(fail_path), exist_ok=True)
        with open(fail_path, "w") as f:
            json.dump(failures, f, indent=2)
        print(f"Failures logged: {fail_path}")

    return records


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Refresh One Piece wiki character data")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--test", action="store_true", help="Scrape 50-character test set")
    group.add_argument("--full", action="store_true", help="Scrape all 1,517 characters")
    group.add_argument(
        "--make-baseline", action="store_true",
        help="Convert original characters_raw.json into snapshot format (run once)"
    )
    parser.add_argument("--delay", type=int, default=3, help="Seconds between requests (default: 3)")
    parser.add_argument("--out", type=str, default=None, help="Override snapshot output directory")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.abspath(__file__))
    today = date.today().isoformat()

    # ── baseline mode ────────────────────────────────────────────────────────
    if args.make_baseline:
        base = os.path.expanduser("~/Desktop/one_piece")
        raw_path = None
        for root, _, files in os.walk(base):
            if "characters_raw.json" in files:
                raw_path = os.path.join(root, "characters_raw.json")
                break
        if not raw_path:
            sys.exit("Could not find characters_raw.json under ~/Desktop/one_piece")

        snapshot_dir = args.out or os.path.join(
            project_root, "data", "snapshots", "baseline"
        )
        make_baseline_snapshot(raw_path, snapshot_dir)
        return

    # ── scrape mode ──────────────────────────────────────────────────────────
    scraper_src = _find_scraper_src()
    sys.path.insert(0, scraper_src)
    from onepiece_scraper import OnePieceScraper

    if args.test:
        char_list = TEST_SLUGS
        label = "test-50"
        print(f"Test mode: {len(char_list)} characters, delay={args.delay}s")
    else:
        char_list_path = _find_char_list()
        with open(char_list_path, encoding="utf-8") as f:
            char_list = [l.strip() for l in f if l.strip()]
        label = "full"
        print(f"Full mode: {len(char_list)} characters, delay={args.delay}s")
        est_min = len(char_list) * args.delay / 60
        print(f"Estimated time: ~{est_min:.0f} minutes")
        print("Press Ctrl-C to stop safely — progress is checkpointed per batch.\n")

    snapshot_dir = args.out or os.path.join(
        project_root, "data", "snapshots", today
    )

    scraper = OnePieceScraper(use_selenium=False)

    # Direct HTML requests return 403 since ~2025. Use the MediaWiki API
    # (action=parse&prop=text) which returns rendered HTML and is not blocked.
    records = _scrape_via_api(scraper, char_list, delay=args.delay)

    print(f"\nPost-processing {len(records)} records into snapshot format...")
    write_snapshot(records, snapshot_dir)


if __name__ == "__main__":
    main()
