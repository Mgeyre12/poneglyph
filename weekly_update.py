"""
weekly_update.py
----------------
Full weekly refresh pipeline. Run every Sunday night; review Monday morning.

Steps:
  1. pipeline/refresh_data.py --full          → fresh snapshot from wiki (~75 min)
  2. pipeline/diff_snapshots.py <prev> <new>  → field-level diff
  3. pipeline/apply_patch.py --apply <diff>   → apply field updates to graph
  4. pipeline/detect_new_content.py           → find new chapters + characters
  5. pipeline/ingest_new_chapters.py --apply  → auto-ingest new chapters
  6. pipeline/stage_new_characters.py         → stage new characters to pending_review

Usage:
  python weekly_update.py             # full run (~75 min)
  python weekly_update.py --dry-run   # preview — no Neo4j writes, no scrape
"""

import sys
import os
import json
import re
import glob
import argparse
import subprocess
from datetime import datetime, date

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(ROOT, "logs", "weekly_runs")


# ── logging ───────────────────────────────────────────────────────────────────

def make_logger(log_path: str):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    f = open(log_path, "w", encoding="utf-8")

    def log(msg: str = ""):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        f.write(line + "\n")
        f.flush()

    def log_raw(text: str):
        f.write(text)
        f.flush()

    def close():
        f.close()

    return log, log_raw, close


# ── snapshot helpers ──────────────────────────────────────────────────────────

def list_dated_snapshots() -> list[str]:
    """Return sorted list of dated snapshot directory names (excluding baseline)."""
    snap_dir = os.path.join(ROOT, "data", "snapshots")
    if not os.path.isdir(snap_dir):
        return []
    entries = [
        d for d in os.listdir(snap_dir)
        if re.match(r"\d{4}-\d{2}-\d{2}$", d)
        and os.path.isdir(os.path.join(snap_dir, d, "characters"))
    ]
    return sorted(entries)


def find_prior_snapshot(exclude_date: str) -> str | None:
    """Return path to most recent snapshot that isn't exclude_date."""
    dated = [d for d in list_dated_snapshots() if d != exclude_date]
    if not dated:
        return None
    return os.path.join(ROOT, "data", "snapshots", dated[-1])


def find_latest_diff() -> str | None:
    """Return path to most recent diff JSON file."""
    diff_dir = os.path.join(ROOT, "diff")
    if not os.path.isdir(diff_dir):
        return None
    files = sorted(glob.glob(os.path.join(diff_dir, "*_diff.json")))
    return files[-1] if files else None


# ── step runner ───────────────────────────────────────────────────────────────

def run_step(
    name: str,
    cmd: list[str],
    log,
    log_raw,
    abort_on_error: bool = True,
) -> tuple[bool, str]:
    """
    Run a subprocess step. Returns (success, stdout_text).
    Logs stdout+stderr. If abort_on_error and it fails, exits the process.
    """
    log(f"▶ {name}")
    log(f"  cmd: {' '.join(cmd)}")
    t0 = datetime.now()

    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=ROOT
    )

    elapsed = (datetime.now() - t0).total_seconds()
    combined = result.stdout + (("\n[stderr]\n" + result.stderr) if result.stderr.strip() else "")
    log_raw(combined)

    if result.returncode == 0:
        log(f"  ✓ done ({elapsed:.0f}s)")
    else:
        log(f"  ✗ FAILED (exit {result.returncode}, {elapsed:.0f}s)")
        if result.stderr.strip():
            log(f"  stderr: {result.stderr.strip()[:300]}")
        if abort_on_error:
            log(f"\nABORTED at step: {name}")
            log(f"Check log for details.")
            sys.exit(1)

    return result.returncode == 0, result.stdout


# ── summary helpers ───────────────────────────────────────────────────────────

def parse_diff_summary(today: str) -> dict | None:
    diff_path = os.path.join(ROOT, "diff", f"{today}_diff.json")
    if not os.path.exists(diff_path):
        return None
    with open(diff_path) as f:
        diff = json.load(f)
    return diff.get("summary", {})


_LOC_OCC_FIELDS = {"Origin", "Residence", "Occupations"}

def diff_has_loc_occ_changes(diff_path: str | None) -> tuple[bool, int]:
    """
    Check whether the diff JSON contains any changes to Origin, Residence,
    or Occupations fields. Returns (has_changes, count_of_affected_chars).
    """
    if not diff_path or not os.path.exists(diff_path):
        return False, 0
    with open(diff_path) as f:
        diff = json.load(f)
    affected = [
        entry for entry in diff.get("changed", [])
        if any(fc["field"] in _LOC_OCC_FIELDS for fc in entry.get("field_changes", []))
    ]
    return bool(affected), len(affected)


def parse_chapters_ingested(stdout: str) -> tuple[int, str]:
    """Extract count and range from ingest_new_chapters.py output."""
    m = re.search(r"Gap\s*:\s*(\d+) chapters \((\d+)[–-](\d+)\)", stdout)
    if m:
        return int(m.group(1)), f"{m.group(2)}–{m.group(3)}"
    m2 = re.search(r"Graph is already up to date", stdout)
    if m2:
        return 0, "—"
    return 0, "unknown"


def count_pending() -> tuple[int, str | None]:
    """Count pending review files and find today's REVIEW doc."""
    pending_dir = os.path.join(ROOT, "data", "pending_review")
    if not os.path.isdir(pending_dir):
        return 0, None
    jsons = [f for f in os.listdir(pending_dir)
             if f.endswith(".json") and not f.startswith("REVIEW_")]
    today = date.today().isoformat()
    review_path = os.path.join(pending_dir, f"REVIEW_{today}.md")
    review = review_path if os.path.exists(review_path) else None
    return len(jsons), review


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Weekly One Piece graph refresh pipeline.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview steps only — no Neo4j writes, no wiki scrape."
    )
    args = parser.parse_args()

    today = date.today().isoformat()
    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    log_path = os.path.join(LOG_DIR, f"{now_str}.log")
    log, log_raw, close_log = make_logger(log_path)

    mode = "DRY-RUN" if args.dry_run else "FULL"
    log(f"{'='*60}")
    log(f"Poneglyph weekly update — {today} [{mode}]")
    log(f"Log: {log_path}")
    log(f"{'='*60}")
    log()

    # ── Step 1: Refresh snapshot ──────────────────────────────────────────────
    log("── Step 1: Refresh snapshot from wiki ──────────────────────")
    if args.dry_run:
        log("  [DRY-RUN] Would run: python pipeline/refresh_data.py --full")
        log("  Skipped — scrape takes ~75 min and hits the wiki.")
        new_snapshot_date = today
        new_snapshot_dir = os.path.join(ROOT, "data", "snapshots", today)
        log(f"  Assumed new snapshot: {new_snapshot_dir}")
    else:
        ok, _ = run_step(
            "pipeline/refresh_data.py --full",
            [sys.executable, os.path.join("pipeline", "refresh_data.py"), "--full"],
            log, log_raw,
        )
        new_snapshot_date = today
        new_snapshot_dir = os.path.join(ROOT, "data", "snapshots", today)
    log()

    # ── Step 2: Diff snapshots ────────────────────────────────────────────────
    log("── Step 2: Diff against previous snapshot ──────────────────")
    prior_dir = find_prior_snapshot(new_snapshot_date)
    diff_json_path = os.path.join(ROOT, "diff", f"{today}_diff.json")

    if args.dry_run:
        if prior_dir:
            log(f"  [DRY-RUN] Would run: python pipeline/diff_snapshots.py {prior_dir} {new_snapshot_dir}")
        else:
            log("  [DRY-RUN] No prior snapshot found — diff would be skipped.")
        log("  Skipped.")
        # For dry-run step 3, fall back to most recent existing diff
        diff_json_path = find_latest_diff() or diff_json_path
    else:
        if not prior_dir:
            log("  WARNING: No prior snapshot found — skipping diff and patch.")
            diff_json_path = None
        else:
            log(f"  Prior snapshot: {prior_dir}")
            log(f"  New snapshot:  {new_snapshot_dir}")
            run_step(
                "pipeline/diff_snapshots.py",
                [sys.executable, os.path.join("pipeline", "diff_snapshots.py"), prior_dir, new_snapshot_dir],
                log, log_raw,
            )
    log()

    # ── Step 3: Apply patch ───────────────────────────────────────────────────
    log("── Step 3: Apply field-level patch ─────────────────────────")
    if diff_json_path and os.path.exists(diff_json_path):
        if args.dry_run:
            run_step(
                "pipeline/apply_patch.py --dry-run",
                [sys.executable, os.path.join("pipeline", "apply_patch.py"), "--dry-run", diff_json_path],
                log, log_raw,
            )
        else:
            run_step(
                "pipeline/apply_patch.py --apply",
                [sys.executable, os.path.join("pipeline", "apply_patch.py"), "--apply", diff_json_path],
                log, log_raw,
            )
    else:
        log("  No diff file found — skipping patch step.")
    log()

    # ── Step 4: Detect new content ────────────────────────────────────────────
    log("── Step 4: Detect new chapters + characters ─────────────────")
    run_step(
        "pipeline/detect_new_content.py",
        [sys.executable, os.path.join("pipeline", "detect_new_content.py")],
        log, log_raw,
    )
    log()

    # ── Step 5: Ingest new chapters ───────────────────────────────────────────
    log("── Step 5: Ingest new chapters ──────────────────────────────")
    if args.dry_run:
        _, ch_stdout = run_step(
            "pipeline/ingest_new_chapters.py (dry-run)",
            [sys.executable, os.path.join("pipeline", "ingest_new_chapters.py")],
            log, log_raw,
        )
    else:
        _, ch_stdout = run_step(
            "pipeline/ingest_new_chapters.py --apply",
            [sys.executable, os.path.join("pipeline", "ingest_new_chapters.py"), "--apply"],
            log, log_raw,
        )
    log()

    # ── Step 6: Stage new characters ─────────────────────────────────────────
    log("── Step 6: Stage new characters ─────────────────────────────")
    run_step(
        "pipeline/stage_new_characters.py",
        [sys.executable, os.path.join("pipeline", "stage_new_characters.py")],
        log, log_raw,
    )
    log()

    # ── Step 7: Refresh location / occupation relationships ───────────────────
    log("── Step 7: Refresh location / occupation relationships ──────")
    loc_occ_changed, loc_occ_count = diff_has_loc_occ_changes(diff_json_path)

    if args.dry_run:
        log("  [DRY-RUN] Would check diff for Origin/Residence/Occupations changes.")
        log("  [DRY-RUN] Would run import_locations.py --apply and import_occupations.py --apply if any found.")
    elif loc_occ_changed:
        log(f"  {loc_occ_count} character(s) have changed Origin/Residence/Occupations — refreshing...")
        run_step(
            "ingest/import_locations.py --apply",
            [sys.executable, os.path.join("ingest", "import_locations.py"), "--apply"],
            log, log_raw,
            abort_on_error=False,
        )
        run_step(
            "ingest/import_occupations.py --apply",
            [sys.executable, os.path.join("ingest", "import_occupations.py"), "--apply"],
            log, log_raw,
            abort_on_error=False,
        )
        log("  NOTE: Stale location/occupation rels are NOT removed — only new data is added.")
        log("  To remove stale rels, re-run imports manually and verify logs/residence_splits.log.")
    else:
        log("  No Origin/Residence/Occupations changes in diff — step skipped.")
    log()

    # ── Final summary ─────────────────────────────────────────────────────────
    log(f"{'='*60}")
    log(f"WEEKLY UPDATE COMPLETE [{mode}]")
    log(f"{'='*60}")
    log()

    # Diff summary
    if not args.dry_run:
        diff_summary = parse_diff_summary(today)
        if diff_summary:
            log(f"  Snapshot diff:")
            log(f"    New chars    : {diff_summary.get('new', '?')}")
            log(f"    Removed chars: {diff_summary.get('removed', '?')}")
            log(f"    Changed chars: {diff_summary.get('changed', '?')}")
            log(f"    Unchanged    : {diff_summary.get('unchanged', '?')}")
            log()

    # Chapters
    ch_count, ch_range = parse_chapters_ingested(ch_stdout)
    if ch_count > 0:
        log(f"  Chapters ingested: {ch_count} ({ch_range})")
    else:
        log(f"  Chapters: graph is up to date (0 new)")

    # Staged characters
    pending_count, review_path = count_pending()
    if pending_count > 0:
        log(f"  Characters staged for review: {pending_count}")
        if review_path:
            log(f"    Review doc: {review_path}")
    else:
        log(f"  Characters: nothing new to stage")

    # Location / occupation refresh
    if not args.dry_run:
        if loc_occ_changed:
            log(f"  Location/Occupation refresh: ran ({loc_occ_count} chars had field changes)")
        else:
            log(f"  Location/Occupation refresh: skipped (no field changes)")

    log()
    log(f"  Log: {log_path}")
    log()

    if pending_count > 0:
        log(f"  ┌─ NEXT ACTION ──────────────────────────────────────────┐")
        log(f"  │  Review staged characters, then promote:               │")
        log(f"  │    python pipeline/promote_pending.py --list                    │")
        log(f"  │    python pipeline/promote_pending.py --promote <slug> --apply  │")
        log(f"  └────────────────────────────────────────────────────────┘")
    else:
        log(f"  Graph is up to date. Nothing pending review.")

    close_log()


if __name__ == "__main__":
    main()
