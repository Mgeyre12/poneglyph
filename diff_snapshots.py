"""
diff_snapshots.py
-----------------
Field-level diff between two snapshot directories.

Usage:
  python diff_snapshots.py <old_dir> <new_dir>
  python diff_snapshots.py data/snapshots/baseline data/snapshots/2026-04-21

Output:
  diff/YYYY-MM-DD_diff.md   — human-readable report
  diff/YYYY-MM-DD_diff.json — machine-readable, consumed by apply_patch.py
"""

import sys
import os
import json
import hashlib
from datetime import date, datetime


# ── load snapshot dir ─────────────────────────────────────────────────────────

def load_snapshot(snapshot_dir: str) -> dict[str, dict]:
    """
    Load all character JSON files from a snapshot directory.
    Returns { slug: record_dict } where _meta is included.
    """
    char_dir = os.path.join(snapshot_dir, "characters")
    if not os.path.isdir(char_dir):
        sys.exit(f"No 'characters/' subdirectory found in: {snapshot_dir}")

    records = {}
    for fname in os.listdir(char_dir):
        if not fname.endswith(".json"):
            continue
        slug = fname[:-5]  # strip .json
        with open(os.path.join(char_dir, fname), encoding="utf-8") as f:
            records[slug] = json.load(f)
    return records


# ── content hash ──────────────────────────────────────────────────────────────

META_FIELDS = {"_meta", "source_url"}


def get_content_fields(record: dict) -> dict:
    """Return only the content fields of a record (no _meta, no source_url)."""
    return {k: v for k, v in record.items() if k not in META_FIELDS}


def compute_hash(record: dict) -> str:
    content = get_content_fields(record)
    serialized = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()


def get_stored_hash(record: dict) -> str | None:
    return record.get("_meta", {}).get("content_hash")


# ── field-level diff ──────────────────────────────────────────────────────────

def diff_fields(old: dict, new: dict) -> list[dict]:
    """
    Compare content fields of two records.
    Returns list of { field, old_value, new_value } for every changed field.
    """
    old_content = get_content_fields(old)
    new_content = get_content_fields(new)

    changes = []
    all_fields = set(old_content) | set(new_content)

    for field in sorted(all_fields):
        old_val = old_content.get(field)
        new_val = new_content.get(field)
        if old_val != new_val:
            changes.append({
                "field": field,
                "old": old_val,
                "new": new_val,
            })
    return changes


# ── main diff ─────────────────────────────────────────────────────────────────

def diff_snapshots(old_dir: str, new_dir: str) -> dict:
    """
    Compare two snapshot directories at the field level.
    Returns a structured diff dict.
    """
    print(f"Loading old snapshot: {old_dir}")
    old = load_snapshot(old_dir)
    print(f"  {len(old)} characters")

    print(f"Loading new snapshot: {new_dir}")
    new = load_snapshot(new_dir)
    print(f"  {len(new)} characters\n")

    old_slugs = set(old)
    new_slugs = set(new)

    new_chars = sorted(new_slugs - old_slugs)
    removed_chars = sorted(old_slugs - new_slugs)
    common = old_slugs & new_slugs

    changed = []
    unchanged_count = 0

    for slug in sorted(common):
        old_rec = old[slug]
        new_rec = new[slug]

        old_hash = get_stored_hash(old_rec) or compute_hash(old_rec)
        new_hash = get_stored_hash(new_rec) or compute_hash(new_rec)

        if old_hash == new_hash:
            unchanged_count += 1
        else:
            field_changes = diff_fields(old_rec, new_rec)
            if field_changes:
                changed.append({
                    "slug": slug,
                    "wiki_url": new_rec.get("source_url", ""),
                    "field_changes": field_changes,
                })

    return {
        "generated_at": datetime.now().isoformat(),
        "old_snapshot": old_dir,
        "new_snapshot": new_dir,
        "summary": {
            "new": len(new_chars),
            "removed": len(removed_chars),
            "changed": len(changed),
            "unchanged": unchanged_count,
            "total_old": len(old),
            "total_new": len(new),
        },
        "new": [
            {
                "slug": s,
                "wiki_url": new[s].get("source_url", ""),
                "fields": get_content_fields(new[s]),
            }
            for s in new_chars
        ],
        "removed": [
            {
                "slug": s,
                "wiki_url": old[s].get("source_url", ""),
            }
            for s in removed_chars
        ],
        "changed": changed,
    }


# ── markdown report ───────────────────────────────────────────────────────────

def render_markdown(diff: dict) -> str:
    s = diff["summary"]
    lines = [
        f"# Snapshot Diff Report",
        f"",
        f"**Generated:** {diff['generated_at']}",
        f"**Old:** `{diff['old_snapshot']}`",
        f"**New:** `{diff['new_snapshot']}`",
        f"",
        f"## Summary",
        f"",
        f"| Category | Count |",
        f"|---|---|",
        f"| New characters | {s['new']} |",
        f"| Removed characters | {s['removed']} |",
        f"| Changed characters | {s['changed']} |",
        f"| Unchanged | {s['unchanged']} |",
        f"| Total (old) | {s['total_old']} |",
        f"| Total (new) | {s['total_new']} |",
        f"",
    ]

    if diff["new"]:
        lines += ["## New Characters", ""]
        for entry in diff["new"]:
            lines.append(f"- **{entry['slug']}** — {entry['wiki_url']}")
        lines.append("")

    if diff["removed"]:
        lines += ["## Removed Characters", ""]
        for entry in diff["removed"]:
            lines.append(f"- **{entry['slug']}** — {entry['wiki_url']}")
        lines.append("")

    if diff["changed"]:
        lines += ["## Changed Characters", ""]
        for entry in diff["changed"]:
            lines.append(f"### {entry['slug']}")
            lines.append("")
            lines.append("| Field | Old | New |")
            lines.append("|---|---|---|")
            for fc in entry["field_changes"]:
                old_v = str(fc["old"])[:80].replace("|", "\\|")
                new_v = str(fc["new"])[:80].replace("|", "\\|")
                lines.append(f"| `{fc['field']}` | {old_v} | {new_v} |")
            lines.append("")

    return "\n".join(lines)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) != 3:
        print("Usage: python diff_snapshots.py <old_dir> <new_dir>")
        sys.exit(1)

    old_dir, new_dir = sys.argv[1], sys.argv[2]

    diff = diff_snapshots(old_dir, new_dir)
    s = diff["summary"]

    print(f"Results: {s['new']} new, {s['removed']} removed, "
          f"{s['changed']} changed, {s['unchanged']} unchanged")

    today = date.today().isoformat()
    os.makedirs("diff", exist_ok=True)

    json_path = f"diff/{today}_diff.json"
    md_path = f"diff/{today}_diff.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(diff))

    print(f"\nWritten:")
    print(f"  {md_path}")
    print(f"  {json_path}")


if __name__ == "__main__":
    main()
