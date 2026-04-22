# Poneglyph V1 Triage

**Date:** 2026-04-22 (Week 9)  
**Source:** Full sweep of MY_PROJECT_NOTES.md weeks 1–8, git history audit, live code review.  
**Standard:** V1_BLOCKER = embarrasses us at public launch or creates a security hole. "It would be cool" = V2.

---

## V1_BLOCKERS (2 items)

### BLOCKER-1 — Hardcoded Neo4j password in every script

**Issue:** `NEO4J_PASSWORD = "Mussa1234"` (or `PASSWORD = "Mussa1234"`) is hardcoded in 15+ files across `ingest/`, `fixes/`, `utils/`, `query/ask.py`, `apply_patch.py`, `detect_new_content.py`, `ingest_new_chapters.py`, `stage_new_characters.py`, `promote_pending.py`, and `weekly_update.py`. It is also present in git history across many commits.

**Why V1_BLOCKER:**  
Making the repo public with a hardcoded credential in every file — even a local-only one — is bad practice that sets the wrong tone for a public OSS project. More critically, the Aura migration in Stage 4 introduces a real cloud credential. Every script must read from env vars before that migration happens or the cloud password will end up hardcoded the same way.

The Anthropic API key is already handled correctly (`os.environ.get("ANTHROPIC_API_KEY")` in `ask.py`) — only the Neo4j password needs fixing.

**`Mussa1234` in git history:** The password is in git history. Since it is a local-only credential (bolt://localhost:7687, no network exposure), rotating it now is not urgent — but after Aura migration the old password becomes irrelevant anyway. No history rewrite needed.

**Fix:** Replace all hardcoded Neo4j constants with `os.getenv()` calls backed by a `.env` file. Create `.env.example`. Update all 15 scripts.

**Estimated time:** 2–3 hours (mechanical, but must be complete before Stage 4 Aura migration).

---

### BLOCKER-2 — Garling counted as a 6th Five Elder

**Issue:** Garling Figarland has an `AFFILIATED_WITH` edge to the "Five Elders" organization node. When a fan asks "Who are the Five Elders?", the graph returns 6 characters (the actual 5 + Garling). The count and the list are factually wrong.

**Why V1_BLOCKER:**  
"Who are the Five Elders?" is one of the top 10 fan lore questions. A public launch where the first thing a user asks is "how many results?" and the answer is 6 instead of 5 is immediately credibility-destroying. This is not a data-absent "we don't know" situation — it's an actively wrong answer.

The affiliation edge itself is arguably correct (Garling IS associated with that org-level grouping), but the query returns him as a peer of the Five which he is not. Fix is in the schema doc and Cypher prompt — tell the LLM that the "Five Elders" org has exactly 5 canonical members and Garling is the Supreme Commander, not one of the five.

**Fix:** Add a schema doc annotation on the Five Elders org explaining the Garling situation. Add a prompt rule (Rule 12) instructing the LLM to note when "Five Elders" queries return more than 5 rows and to identify Garling by role rather than as a member.

**Estimated time:** 30 minutes.

---

## V1_POLISH (5 items — only worth touching if trivially cheap)

### POLISH-1 — Kaku name collision
Two characters named "Kaku" (CP9 debut Ch 323, Kyoshiro Family debut Ch 927). A query for "who is Kaku" returns both, and the LLM may conflate them or describe one while ignoring the other.

**Mitigation:** Add a schema doc note for disambiguation queries: when multiple characters share a name, the LLM should list both with debut chapter. No graph change required.  
**Effort:** 20 min.

### POLISH-2 — Character nodes with status "Destroyed" / "Active"
Two `:Character` nodes have non-standard status values. They are likely non-human entities (ship, weapon) that were scraped into the character list. No direct user impact unless someone queries by status.  
**Mitigation:** Identify and patch status to "Unknown" or filter from results.  
**Effort:** 30 min.

### POLISH-3 — Brannew displayed as "Brandnew"
The name normalization algorithm picked "Brandnew" (first OEN variant) instead of "Brannew". Minor character; low impact.  
`MATCH (c:Character {opwikiID: "Brannew"}) SET c.name = "Brannew"`  
**Effort:** 5 min.

### POLISH-4 — No `.env.example` file
Every env var the project uses needs to be documented in `.env.example` before the repo goes public. This is required by Stage 7 anyway.  
**Effort:** 20 min (created as part of BLOCKER-1 fix).

### POLISH-5 — `run_cypher()` creates a new Neo4j driver per question
The current pipeline opens and closes a driver on every call — fine for a terminal REPL, minor resource waste under API load. Stage 5's service layer will use a shared driver with proper lifecycle management, so this resolves itself.  
**Effort:** 0 (handled in Stage 5).

---

## V2 — Deferred to public roadmap (ROADMAP.md)

| Item | Why deferred |
|---|---|
| Bounty field parse | Source data is concatenated with no separator; needs full raw re-scrape |
| Haki data | Not in source JSON; requires manual curation or new scrape target |
| Age variants (debut / pre-timeskip / current) | Current last-value approach is fine for v1 |
| Birthday date parsing | Raw string is readable; structured date is nice-to-have |
| 72 additional malformed org names | ~40 are single-person orgs; ~20 comma-fusion; complex to clean without data errors |
| Relationship patching in apply_patch.py | Scalar-only patch is safe; rel patching risks duplicates without more logic |
| Full chapter list (all 1100+) | Debut-chapter-only graph is documented; filling gaps needs new data source |
| Kaku CP9 / Kaku Wano disambiguation (full fix) | POLISH-1 mitigation is sufficient |
| Garling / Five Elders (graph-level fix) | Prompt fix is sufficient; graph reclassification is complex |
| Arc name "Elbaf" vs "Elbaf" | Pre-existing discrepancy; documented in notes |
| Slug mismatch audit (wiki vs graph) | ~3 slugs differ; low query impact |
| Answer LLM training data leaks | Deferred by design (prompt hardening is a deeper project) |
| Auto-promote characters after N clean cycles | Nice-to-have pipeline automation |
| Multi-step Cypher reasoning | Agentic improvement; not needed for v1 |
| Web search tool for out-of-graph facts | v2 agentic layer |

---

## Summary

| Bucket | Count |
|---|---|
| V1_BLOCKER | 2 |
| V1_POLISH | 5 (3 trivially cheap, 1 is part of BLOCKER-1, 1 is zero-effort) |
| V2 | 14 |

**Real work before Stage 2:** BLOCKER-1 (env vars across 15 scripts, ~2-3h) + BLOCKER-2 (prompt/schema fix, ~30m). Total: ~3-4 hours.
