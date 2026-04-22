"""
run_stress_test.py
------------------
Runs all questions from stress_test_questions.md through the ask.py pipeline
and writes structured results to stress_test_run_1.md (or run_2.md, etc.).

Usage:
  python tests/run_stress_test.py           # writes run_1.md
  python tests/run_stress_test.py 2         # writes run_2.md
"""

import sys
import os
import time
import re

# Make query/ importable from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from query.ask import (
    get_client,
    load_schema,
    question_to_cypher,
    validate_cypher,
    run_cypher,
    results_to_answer,
    SCHEMA_FILE,
)

QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "stress_test_questions.md")
THIS_DIR = os.path.dirname(__file__)


# ── parse questions from markdown ─────────────────────────────────────────────


def parse_questions(path: str) -> list[dict]:
    """Parse stress_test_questions.md → list of {num, category, question}."""
    questions = []
    current_category = "Unknown"
    category_re = re.compile(r"^##\s+Category\s+\d+\s+[—–-]+\s+(.+)", re.IGNORECASE)
    question_re = re.compile(r"^(\d+)\.\s+(.+)")

    with open(path) as f:
        for line in f:
            line = line.rstrip()
            m = category_re.match(line)
            if m:
                current_category = m.group(1).strip()
                continue
            m = question_re.match(line)
            if m:
                questions.append(
                    {
                        "num": int(m.group(1)),
                        "category": current_category,
                        "question": m.group(2).strip(),
                    }
                )
    return questions


# ── run one question through the full pipeline ────────────────────────────────


def run_one(q: dict, client, schema: str) -> dict:
    result = {
        "num": q["num"],
        "category": q["category"],
        "question": q["question"],
        "cypher": "",
        "validation": "",
        "cypher_ok": False,
        "row_count": 0,
        "answer": "",
        "latency_s": 0.0,
        "status": "FAIL",
    }

    t0 = time.time()

    try:
        cypher = question_to_cypher(client, q["question"], schema)
        result["cypher"] = cypher
    except Exception as e:
        result["answer"] = f"[cypher generation error] {e}"
        result["latency_s"] = round(time.time() - t0, 2)
        return result

    valid, reason = validate_cypher(cypher)
    result["validation"] = reason

    if not valid:
        result["answer"] = f"[validation rejected] {reason}"
        result["latency_s"] = round(time.time() - t0, 2)
        return result

    result["cypher_ok"] = True

    try:
        rows = run_cypher(cypher)
        result["row_count"] = len(rows)
    except Exception as e:
        result["answer"] = f"[neo4j error] {e}"
        result["latency_s"] = round(time.time() - t0, 2)
        return result

    try:
        answer = results_to_answer(client, q["question"], cypher, rows)
        result["answer"] = answer
        result["status"] = "PASS"
    except Exception as e:
        result["answer"] = f"[answer generation error] {e}"

    result["latency_s"] = round(time.time() - t0, 2)
    return result


# ── markdown output ───────────────────────────────────────────────────────────


def build_summary(results: list[dict]) -> str:
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = total - passed
    avg_lat = round(sum(r["latency_s"] for r in results) / total, 2) if total else 0

    # per-category stats
    cats: dict[str, dict] = {}
    for r in results:
        c = r["category"]
        cats.setdefault(c, {"pass": 0, "total": 0})
        cats[c]["total"] += 1
        if r["status"] == "PASS":
            cats[c]["pass"] += 1

    lines = [
        "## Summary\n",
        f"- **Total questions:** {total}",
        f"- **Passed:** {passed}  |  **Failed:** {failed}  |  **Pass rate:** {round(passed/total*100)}%",
        f"- **Avg latency:** {avg_lat}s\n",
        "### By category\n",
        "| Category | Pass | Total | Rate |",
        "|---|---|---|---|",
    ]
    for cat, s in cats.items():
        rate = round(s["pass"] / s["total"] * 100)
        lines.append(f"| {cat} | {s['pass']} | {s['total']} | {rate}% |")

    return "\n".join(lines)


def build_detail(results: list[dict]) -> str:
    sections = []
    for r in results:
        status_badge = "✅" if r["status"] == "PASS" else "❌"
        block = f"""---

### {r['num']}. {r['question']} {status_badge}

**Category:** {r['category']}
**Latency:** {r['latency_s']}s
**Validation:** {r['validation'] or '—'}
**Rows returned:** {r['row_count']}

<details>
<summary>Generated Cypher</summary>

```cypher
{r['cypher']}
```

</details>

**Answer:**

{r['answer']}
"""
        sections.append(block)
    return "\n".join(sections)


def write_results(results: list[dict], run_num: int) -> str:
    summary = build_summary(results)
    detail = build_detail(results)
    from datetime import datetime

    header = f"# Stress Test Run {run_num}\n\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"
    content = f"{header}\n{summary}\n\n## Results\n\n{detail}\n"

    out_path = os.path.join(THIS_DIR, f"stress_test_run_{run_num}.md")
    with open(out_path, "w") as f:
        f.write(content)
    return out_path


# ── main ──────────────────────────────────────────────────────────────────────


def main():
    run_num = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    print(f"Poneglyph Stress Test — Run {run_num}")
    print("=" * 50)

    questions = parse_questions(QUESTIONS_FILE)
    print(f"Loaded {len(questions)} questions.\n")

    client = get_client()
    schema = load_schema()
    results = []

    for q in questions:
        print(f"[{q['num']:02d}/50] {q['question'][:60]}...", end="", flush=True)
        r = run_one(q, client, schema)
        results.append(r)
        badge = "✅" if r["status"] == "PASS" else "❌"
        print(f" {badge} ({r['latency_s']}s, {r['row_count']} rows)")

    out_path = write_results(results, run_num)

    # print summary to terminal
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"\n{'='*50}")
    print(f"Done. {passed}/{total} passed ({round(passed/total*100)}%)")
    print(f"Results written to: {out_path}")


if __name__ == "__main__":
    main()
