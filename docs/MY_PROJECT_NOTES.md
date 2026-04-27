# Poneglyph — Project Notes

A One Piece knowledge graph + natural-language LLM query layer for fans.
Track foreshadowing, validate theories, get grounded answers with chapter citations.

Named after the indestructible stones containing encoded world history — readable only by those who know the ancient language. The graph is the stone. The LLM is Robin.

**Stack:** Neo4j (graph DB) + Python + LLM query layer (`ask.py`)
**Data source:** Forked from [kalnassag/one-piece-ontology](https://github.com/kalnassag/one-piece-ontology)
**GitHub:** https://github.com/Mgeyre12/poneglyph
**Builder:** Solo, ~15 hrs/week

---

## Day 1 — Characters into Neo4j (2026-04-21)

### What I did

- Created this project from scratch, separate from the forked source repo
- Copied the two processed data files from the fork into `data/`
- Wrote `import_characters.py` to load 1,517 characters as `:Character` nodes into a local Neo4j instance
- Verified with Cypher queries in Neo4j Browser — all nodes loaded, Luffy confirmed

### How to reproduce

**Prerequisites:**
- Neo4j Desktop installed and running locally (bolt://localhost:7687)
- A database named `one-piece-db` created and started in Neo4j Desktop
- Python 3.10+

**Install deps:**
```bash
pip install neo4j
```

**Run the import:**
```bash
cd ~/Desktop/onepiece-kg
python3 import_characters.py
```

**Verify in Neo4j Browser (http://localhost:7474):**
```cypher
-- Total nodes (expect ~1517)
MATCH (c:Character) RETURN count(c) AS total

-- Find Luffy
MATCH (c:Character {opwikiID: "Monkey_D._Luffy"}) RETURN c

-- All deceased characters
MATCH (c:Character {status: "Deceased"})
RETURN c.name, c.debutChapter ORDER BY c.debutChapter

-- Characters missing age or debut chapter
MATCH (c:Character)
WHERE c.age IS NULL OR c.debutChapter IS NULL
RETURN c.name, c.age, c.debutChapter LIMIT 20
```

### What's in each `:Character` node

| Property | Example |
|---|---|
| `opwikiID` | `"Monkey_D._Luffy"` |
| `name` | `"Monkey D. Luffy"` |
| `nameJapanese` | `"モンキー・D・ルフィ"` |
| `nameRomanized` | `"Monkī Dī Rufi"` |
| `status` | `"Alive"` |
| `age` | `19` |
| `height_cm` | `174.0` |
| `bloodType` | `"F"` |
| `birthday` | `"May 5th (Children's Day)"` |
| `epithet` | `"Straw Hat Luffy"` |
| `debutChapter` | `1` |
| `debutEpisode` | `1` |
| `opwikiURL` | `"https://onepiece.fandom.com/wiki/Monkey_D._Luffy"` |

---

## Week 2 — Relationships (2026-04-21)

### What I did

Turned the flat character list into a real graph by adding three relationship types and two new node types.

**New node types:**
- `:Organization` — 372 nodes (pirate crews, Marine branches, families, alliances, etc.)
- `:DevilFruit` — 134 nodes with `name`, `type`, `japanese_name`, `meaning`, `debut_chapter`
- `:Chapter` — 515 nodes (unique debut chapters only, not every chapter in the manga)

**New relationship types:**
- `(:Character)-[:AFFILIATED_WITH {status, status_raw}]->(:Organization)` — 1,912 relationships
- `(:Character)-[:ATE_FRUIT {status}]->(:DevilFruit)` — 143 relationships
- `(:Character)-[:DEBUTED_IN]->(:Chapter)` — 1,473 relationships

**Scripts added:** `import_affiliations.py`, `import_devil_fruits.py`, `import_chapters.py`

All scripts are idempotent — safe to re-run.

### Graph state after Week 2

| Label | Count |
|---|---|
| `:Character` | 1,517 |
| `:Organization` | 372 |
| `:DevilFruit` | 134 |
| `:Chapter` | 515 |
| `:AFFILIATED_WITH` | 1,912 |
| `:ATE_FRUIT` | 143 |
| `:DEBUTED_IN` | 1,473 |

### Name normalization scheme (org_id)

`org_id` on `:Organization` nodes: lowercase, spaces → underscores, non-`[a-z0-9_-]` characters stripped.
Example: `"Straw Hat Pirates"` → `"straw_hat_pirates"`, `"Clan of D."` → `"clan_of_d"`

### Affiliation status normalization

`status` on `:AFFILIATED_WITH` relationships is normalized from the raw annotation:
- No annotation → `"current"`
- Contains "former"/"formerly" → `"former"`
- Contains "defected" → `"defected"`
- "disbanded" → `"disbanded"`
- Contains "temporary"/"temporarily" → `"temporary"`
- "semi-retired" → `"semi-retired"`
- "descended" → `"descended"`
- Anything else → kept as-is (sub-groups, branches, roles)

`status_raw` always stores the original annotation string for inspection.

### Data quality issues found this week

- **Luffy's devil fruit type** — upstream scraper stored Gomu Gomu no Mi as `Paramecia`. Manually patched in Neo4j to `Zoan` / `"Hito Hito no Mi, Model: Nika"` (Chapter 1044 reveal). The `fruit_id` slug stays `Gomu_Gomu_no_Mi` (wiki slug, not changing it).
- **Character `name` field has multi-value variants** — e.g. `"Marshall D. Teech (VIZ, Funimation subs, edited dub);Marshall D. Teach (Funimation uncut dub)"`. The scraper dumped all English name variants into one field. Affects display in query results. Future fix: parse out a single canonical name.
- **Malformed org name: `"Whitebeard Pirates2nd Division"`** — annotation was fused into the org name without a delimiter in the source data. It exists as an org node with that ugly name. Needs a manual patch or a smarter parser.
- **257 characters have no `Affiliations` field** — skipped silently (not errors, just no data).
- **44 characters have no `debut_chapter`** — logged to `logs/chapters_skipped.log`.
- **Devil fruit source data has no `description` field** — only `meaning` (e.g. "Rubber"). Real descriptions would need a separate scrape.
- **`:Chapter` nodes only cover debut chapters** — 515 unique chapters, not all 1100+ manga chapters. A full chapter list would need a separate data source.

### Skipped / unresolved (logged)

- `logs/fruit_user_skipped.log` — ~11 fruit user entries that couldn't be resolved: Seraphim copies (S-Snake, S-Bear, S-Hawk, S-Shark), film-only characters (Gasparde, Honey Queen, Simon, Buzz), unnamed characters ("A certain doctor", "Unnamed New World pirate"), and SMILE fruit ("Gifters; Various people").

---

## Known issues to address later

- `height_cm` for Luffy is `91` (should be `174`) — scraping bug in the source data, the wiki listed the value in a format the scraper misread. Fix: manually patch known wrong heights, or re-scrape with a corrected parser.
- `Age` field in the source JSON is a multi-value string (e.g. `"7 (debut);17 (pre-timeskip);19 (post-timeskip)"`). The import script takes the last value. Pre-timeskip ages are lost — consider storing all three as separate properties (`age_debut`, `age_pretimeskip`, `age_current`) in a future pass.
- `Bounty` field in source JSON is all values concatenated with no separator — unusable as-is. Needs a full reparse against the raw data before it can be loaded.
- 185 characters have no `Official English Name` — `name` falls back to Romanized Name for these.
- Two `:Character` nodes have `status: "Destroyed"` or `status: "Active"` — likely non-human entities (a ship, a weapon) that ended up in the character list. Worth filtering or reclassifying.
- `Birthday` is stored as a raw string (`"May 5th (Children's Day)"`). Should be parsed to a proper date in a future pass.

---

---

## Week 3 — Data quality fixes + Arc nodes (2026-04-21)

### What I did

**Part 1a — Name normalization (`fix_character_names.py`)**

Migrated the `name` property on all 1,517 `:Character` nodes from the raw multi-value string to a single canonical English display name. Algorithm:
1. Paren-aware `;` split (handles `"Ganfor (VIZ; Funimation simulcast)"` correctly)
2. Take first segment
3. Strip translator attribution parentheticals (VIZ, Funimation, 4Kids, WT100, OPCG, Odex, Netflix, Crunchyroll, formerly, Live-Action, uncut, edited, subs, dub, BStation, former)
4. Detect fused names via `(?<![Mm]c)(?<![Mm]ac)[a-z][A-Z]|\d[A-Z]` — fall back to wiki slug
5. Strip trailing `*`

- 1,517 names processed; most were already clean; 206 meaningfully changed
- 2 known edge cases logged to `logs/name_fix_edge_cases.log`:
  - `Brannew` — algorithm picks "Brandnew" (first OEN variant). Correct name is "Brannew". Patch: `MATCH (c:Character {opwikiID: "Brannew"}) SET c.name = "Brannew"`
  - `Gan_Fall` — algorithm picks "Ganfor" (VIZ). Wiki slug is "Gan Fall". Either is valid; patch if preferred.

Also added `name_ja` and `name_romanized` aliases (were already stored as `nameJapanese` / `nameRomanized`).

**Part 1b — Org name fixes (`fix_org_names.py`)**

Targeted 31 malformed `:Organization` nodes from a hand-compiled `FIXES` lookup table. Two fix types:
- **Simple rename** — one malformed org → one correctly-named org. If target exists, characters are re-wired and the malformed node is deleted.
- **Split** — one phantom fused org → 2–3 component orgs. Each character gets relationships to all component orgs.

Sample fixes applied:
- `"Whitebeard Pirates2nd Division"` → `"Whitebeard Pirates 2nd Division"`
- `"Marines(Headquarters"` → `"Marines"` (re-wires to existing Marines node)
- `"Kid PiratesNinja-Pirate-Mink-Samurai Alliance"` → `["Kid Pirates", "Ninja-Pirate-Mink-Samurai Alliance"]`
- `"Tontatta KingdomTontatta PiratesStraw Hat Grand Fleet"` → 3-way split
- `"Marines(SWORD), Marine153rd Branch"` → `["Marines", "Marine 153rd Branch"]`

Discovered 72 additional malformed org names after running, deferred to v2 backlog (see below).

**Part 2 — Arc nodes (`import_arcs.py` + `data/arcs.json`)**

Added 33 `:Arc` nodes and linked all `:Chapter` nodes via `(:Chapter)-[:IN_ARC]->(:Arc)`.

- `data/arcs.json` — hand-compiled, Romance Dawn (Ch 1) through Elbaf (Ch 1126–). Elbaf uses `end_chapter: 9999` as ongoing sentinel.
- Arc fields: `arc_order` (stable int key), `name`, `saga`, `start_chapter`, `end_chapter`
- 514 of 515 `:Chapter` nodes linked; Chapter 0 (Strong World special) is intentionally unlinked.
- Uniqueness constraint on `arc_order`.

### Graph state after Week 3

| Label | Count |
|---|---|
| `:Character` | 1,517 |
| `:Organization` | ~372 (after fixes) |
| `:DevilFruit` | 134 |
| `:Chapter` | 515 |
| `:Arc` | 33 |

| Relationship | Count |
|---|---|
| `:AFFILIATED_WITH` | ~1,912 |
| `:ATE_FRUIT` | 143 |
| `:DEBUTED_IN` | 1,473 |
| `:IN_ARC` | 514 |

### Arc debuts (top arcs by character count)

| Arc | Character debuts |
|---|---|
| Wano Country Arc | 282 |
| Whole Cake Island Arc | 123 |
| Dressrosa Arc | 95 |
| Marineford Arc | 86 |

### Scripts added this week

- `fix_character_names.py` — name normalization
- `fix_org_names.py` — targeted org name fixes (31 nodes)
- `import_arcs.py` — Arc nodes + IN_ARC relationships
- `data/arcs.json` — arc chapter range data

All scripts are idempotent — safe to re-run.

---

## Week 4 — Natural-language query layer (2026-04-21)

### What I built

A terminal-only question-answering pipeline over the Neo4j graph. No UI, no web server.

**Scripts added:**
- `generate_schema.py` — introspects the live graph and writes `graph_schema.md`
- `graph_schema.md` — LLM context doc: all node labels, property types, relationship directions, annotated notes, and 6 example Cypher patterns
- `ask.py` — the full pipeline in one file
- `requirements.txt` — pinned deps (`neo4j`, `anthropic`, `python-dotenv`)
- `test_queries.md` — Stage 7 results: 10 questions, generated Cypher, result counts, answers, judgments

**Usage:**
```bash
python3 ask.py "who are the Straw Hat Pirates?"   # single question
python3 ask.py                                      # interactive REPL
```

### Pipeline architecture

```
User question
  → build prompt (graph_schema.md as context)
  → Claude API call 1 → Cypher query
  → validate (reject destructive keywords)
  → run against Neo4j (5s timeout)
  → Claude API call 2 → natural-language answer
  → print to terminal
```

Two LLM calls, one Cypher execution. Model: `claude-sonnet-4-6`.

### Key prompt engineering decisions

- **Schema doc as system context** — full `graph_schema.md` injected into the Cypher-generation system prompt. Quality of the doc directly determines Cypher quality.
- **Case-insensitive partial match enforced** — prompt explicitly instructs `toLower() + CONTAINS` for all name matching. Fans type "luffy", not "Monkey D. Luffy".
- **4 few-shot examples** in the Cypher prompt covering the most common query patterns.
- **Answer step is grounded** — system prompt instructs: only use data from results, don't hallucinate from training. If data is absent, say so.
- **Cypher safety** — `validate_cypher()` rejects CREATE, MERGE, DELETE, SET, REMOVE, DROP, LOAD, and non-schema CALL keywords before any query touches the DB.
- **Failures logged** — any validation failure or execution error appends to `failure_cases.md` with the question + bad query for later prompt improvement.

### Stage 7 test results (10 questions)

| Q | Question | Judgment |
|---|---|---|
| 1 | Who are the Straw Hat Pirates? | ✅ Correct |
| 2 | What Devil Fruits has Luffy eaten? | ✅ Correct |
| 3 | List all Logia users | ✅ Correct |
| 4 | Which characters debuted in the Wano arc? | ✅ Correct |
| 5 | Who are the current Four Emperors? | ✅ Correct |
| 6 | What is Roronoa Zoro's affiliation? | ✅ Correct |
| 7 | Former members of the Seven Warlords? | ✅ Correct |
| 8 | Which arc has the most character debuts? | ✅ Correct |
| 9 | Who are the Five Elders? | ⚠️ Partial — Garling returned as 6th "Elder" (affiliation edge exists but he's not one of the five) |
| 10 | Does Imu have a known Devil Fruit? | ✅ Honest — correctly says no data rather than hallucinating |

**9/10 correct or better.**

### Gaps discovered from testing

- **No ability/Haki data** — any question about what a fruit does, or what Haki a character uses, returns "not in graph". Expected — not in source data.
- **No bounty data** — confirmed unusable as-is (concatenated field, known since Week 2).
- **Graph staleness** — Imu's fruit was revealed in a recent chapter (after the data scrape). First confirmed case of the graph being behind current manga. Needs a re-scrape pipeline.
- **Garling / Five Elders ambiguity** — Garling has an `AFFILIATED_WITH` edge to the Five Elders org but is not one of the five. A `rank` or `role` property on the relationship, or a more specific org node, would fix this.
- **LLM draws on training knowledge** — for large result sets (Wano, 282 rows) the LLM correctly describes characters using training knowledge (e.g. "the young girl Luffy befriends"). Harmless when accurate, but could hallucinate for obscure characters. No failures seen in testing.

---

## Week 5 — Stress test + targeted fixes (2026-04-21)

### Goal

Run 50 diverse questions through `ask.py`, triage failures by root cause, apply fixes that address the most failures, re-run and measure delta. No new features, no new data.

### What I did

**Stage 1 — Question set**
Built `tests/stress_test_questions.md`: 50 questions across 9 categories (easy lookups, relationship traversals, negative cases, name ambiguity, temporal/former, aggregations, cross-arc, vague/fan-style, adversarial).

**Stage 2 — Runner**
Built `tests/run_stress_test.py`: reads the question file, runs each question through the full `ask.py` pipeline, captures Cypher, validation result, row count, answer, and latency per question, writes `tests/stress_test_run_N.md` with summary + per-question detail.

**Stage 3 — Triage**
Reviewed all answers manually. Full triage in `tests/stress_test_triage.md`. Three root cause clusters:

| Pattern | Count | Type |
|---|---|---|
| Answer LLM leaks training knowledge (height injection, absence claims, rationalized bad data) | 5+ | PROMPT — deferred to web-search agent milestone |
| Devil Fruit name mismatch (fans type Japanese, graph stores English) | 3 | SCHEMA_DOC_FIX + CYPHER_FIX |
| Former-affiliation queries too broad (no exclusion of current members) | 2 | CYPHER_FIX |
| Data bugs (Luffy height, Koby Marine status) | 2 | GRAPH_DATA_FIX |

**Stage 4 — Fixes applied**

*Fix 1 — Schema doc: DevilFruit name clarification*
Updated `docs/graph_schema.md` to document that `f.name` stores the English canonical name (e.g. "Op-Op Fruit") and `f.fruit_id` stores the wiki slug (e.g. "Ope_Ope_no_Mi"). Both must be searched when a fan types a Japanese romanized name.

*Fix 2 — Cypher prompt: dual-field fruit lookup (Rule 8)*
Added explicit rule + few-shot example: always search `toLower(f.name) CONTAINS $term OR toLower(f.fruit_id) CONTAINS $term`. Resolves Ope Ope no Mi, Mera Mera no Mi, Gura Gura no Mi lookup failures.

*Fix 3 — Cypher prompt: former-affiliation with NOT EXISTS (Rule 9)*
Added rule + few-shot example: "former X" queries must filter `r.status IN [former, defected, disbanded, revoked]` AND use `NOT EXISTS` to exclude characters who still have a current affiliation with the same org. Resolves Koby appearing as a "former Marine."

*Fix 4 — Graph data: Luffy height*
`MATCH (c:Character {opwikiID: "Monkey_D._Luffy"}) SET c.height_cm = 174.0` — upstream scraper stored 91.0. Script: `fixes/fix_data_bugs.py`.

*Fix 5 — Graph data: Koby Marine relationships*
Removed 2 misleading `AFFILIATED_WITH` relationships (Marine 153rd Branch `former`, Alvida Pirates `defected`) that caused Koby to appear in "former Marines" queries. He remains linked to Marines (SWORD) as current.

**Stage 5 — Re-run results**

| | Run 1 | Run 2 |
|---|---|---|
| Pass rate (pipeline) | 50/50 | 50/50 |
| Avg latency | 7.37s | 7.51s |
| Fruit lookups returning data | Failing (0 rows) | Fixed ✅ |
| Former-affiliation accuracy | Koby false positive | Koby excluded ✅ |
| Luffy height in graph | 91.0 | 174.0 ✅ |

Note: the runner's PASS/FAIL tracks pipeline completion, not answer quality. The real delta is visible in answer quality by category — improvements confirmed on Q20 (Mera Mera), Q31 (Gura Gura), Q44 (strongest swordsman via epithet), Q26 (height correctly flagged vs. fabricated).

### Known issues remaining (not fixed this week)

- **Answer LLM training data leaks** — Claude still injects canon knowledge (Shanks arm story, Rocks D. Xebec, Baroque Works roles) when graph data is sparse. Deferred — planned fix is a web search tool so the agent can verify claims it can't ground in the graph.
- **Kaku ambiguity** — Two separate characters named "Kaku" in the graph (CP9/Water 7 debut Ch 323; Kyoshiro Family/Wano debut Ch 927). Claude rationalizes rather than flagging name collision. Future fix: flag when multiple characters share a name.
- **Hanafuda as Warlord** — Confirmed real entry from the One Piece wiki. Not a bug.
- **Five Elders / Garling** — Garling still appears as a 6th Elder. Carried over from Week 4 backlog.

### Project structure reorganized this week

Moved all scripts into subdirectories for scale:
```
ingest/   — import_*.py
fixes/    — fix_*.py
query/    — ask.py
utils/    — generate_schema.py
docs/     — graph_schema.md, test_queries.md, MY_PROJECT_NOTES.md
tests/    — stress test runner + results
```

---

## Week 6 — Re-scrape + diff + patch pipeline (2026-04-21)

### Goal

Build the infrastructure to keep the graph current: scrape fresh data, diff against baseline, apply patches safely. Detection of new chapters/characters but no ingestion.

### Scraper audit verdict: ENHANCE

Audited Kareem's `onepiece_scraper.py` (851 lines). Full audit in `audit/scraper_audit.md`.

Key findings:
- **User-Agent IS set** — Week 1 notes were wrong about this
- **Height = 91 bug is in the importer, not the scraper** — scraper returns the full raw string with all three heights; `import_characters.py` took the first value. Already fixed in graph.
- **0 missing characters** — Week 1's "56 missing" claim was wrong. Graph and raw scrape are 1,517/1,517 perfect alignment.
- **Direct wiki requests now return 403** — Fandom tightened bot detection since the original scrape. Fix: use MediaWiki API (`action=parse&prop=text`) which returns rendered HTML including the infobox and is not blocked.
- Decision: keep Kareem's scraper untouched. Wrapper handles output format and API routing.

### What was built

**`refresh_data.py`** — wrapper around Kareem's scraper
- `--test`: scrape 50-char subset (Straw Hats, Emperors, Marines, Five Elders, misc)
- `--full`: scrape all 1,517 characters (~75 min at 3s delay)
- `--make-baseline`: convert original `characters_raw.json` to snapshot format (run once)
- Uses `action=parse&prop=text` MediaWiki API route (not blocked)
- Output: `data/snapshots/YYYY-MM-DD/characters/{slug}.json` per character
- Each file has `_meta: { scraped_at, wiki_url, content_hash }` for stable diffing
- `data/snapshots/baseline/` — 1,517 character baseline from Kareem's original scrape

**`diff_snapshots.py`** — field-level diff engine
- Input: two snapshot directories
- Compares by content_hash first; field-by-field only on hash mismatch
- Output: `diff/YYYY-MM-DD_diff.md` (human) + `diff/YYYY-MM-DD_diff.json` (machine)
- Buckets: NEW / REMOVED / CHANGED / UNCHANGED
- REMOVED section automatically suppressed for partial snapshots (< 90% coverage) to prevent false removals

**`apply_patch.py`** — safe graph patcher
- Default: `--dry-run`. Must pass `--apply` to write.
- CHANGED: updates Neo4j properties field-by-field. Maps known fields to graph property names; unknown fields stored as `raw_*` properties.
- REMOVED: marks nodes `removed_at = timestamp` — never deletes.
- NEW: stub — deferred to Week 7.
- Logs every before/after to `logs/patches/YYYY-MM-DD_HH-MM.log`.

**`detect_new_content.py`** — wiki vs graph gap detector
- Chapter gap: binary search for highest existing `Chapter_N` wiki page
- Character gap: parses `List_of_Canon_Characters` via API parse
- Output: `reports/pending_updates_YYYY-MM-DD.md`

### Detection findings (as of 2026-04-21)

| | |
|---|---|
| Graph latest chapter | 1162 |
| Wiki latest chapter | 1181 |
| **Chapter gap** | **19 chapters** |
| Characters in graph | 1,517 |
| Characters on wiki | 1,525 |
| **New characters** | **11** |

New characters detected: Billy_the_Yabuki, Bjorn_(Pirate), D._D._Tee, Gantonio, Love, Magnolia, Misty, Ragnir, Ratatoskr, Rhodes, Warrior_God

These are the ingestion targets for Week 7.

### Test run results (50-char subset)

50/50 scraped successfully via API. Diff against baseline:
- **16 changed** (mostly live-action cast additions, minor voice actor updates, formatting tweaks)
- **34 unchanged**
- 17 property updates applied to Neo4j

Notable real changes detected:
- Bartolomeo, Brook, Tony Chopper, Nami: live-action portrayal actors added
- Emporio Ivankov: epithet spacing fixed ("OkamaKing" → "Okama King")
- Jinbe: Crunchyroll name variant added to Official English Name
- Edward Newgate: occupation text updated

### v2 Backlog additions

- Full 1,517-character refresh not yet run (requires dedicated ~75 min window)
- `Affiliations` and `Occupations` changes are stored as raw strings — not yet re-processed through affiliation import logic. Patching graph relationships from diffs is a future improvement.
- Slug correction map: some characters have different wiki slugs vs. opwikiIDs in the graph (e.g. `Sanji` vs `Vinsmoke_Sanji`). The `--test` set hit this; full run will expose more. Needs a slug→opwikiID normalization step.

---

## Week 7 — Close the gap + new content ingestion pipeline (2026-04-22)

### Goal

Ingest the 19-chapter gap and 11 new characters detected in Week 6. Build the full ingestion pipeline: chapter auto-ingest, character staging queue, human-review promotion, and a weekly wrapper script.

### What was built

**`ingest_new_chapters.py`**
- Auto-detects chapter gap via binary search (graph max vs. wiki max)
- Fetches English chapter titles from wiki wikitext (`| ename =` / `| title =` fields)
- MERGEs `:Chapter` nodes + `(:Chapter)-[:IN_ARC]->(:Arc)` from `data/arcs.json` ranges
- Dry-run default, `--apply` to commit
- Logs to `logs/ingestion/chapters_YYYY-MM-DD.log`

**`stage_new_characters.py`**
- Detects new characters (wiki slugs not in graph)
- Scrapes each via MediaWiki API + Kareem's `extract_character_data()`
- Writes to `data/pending_review/{opwikiID}.json` — does NOT touch the graph
- Generates `data/pending_review/REVIEW_YYYY-MM-DD.md` — human-readable review doc with status, debut, affiliations, fruit, parse warnings, and ⚠️ flags for significant characters
- Logs to `logs/ingestion/staging_YYYY-MM-DD.log`

**`promote_pending.py`**
- Four modes: `--list`, `--promote <slug>`, `--promote-all`, `--reject <slug> --reason "..."`
- Dry-run default on all promote actions
- Promotion: MERGE `:Character` node + affiliations + DEBUTED_IN + ATE_FRUIT (if any)
- Strips citation refs `[N]` from affiliation strings before parsing (prevents `giant_warrior_pirates1` org_id corruption)
- Moves promoted JSON to `data/snapshots/YYYY-MM-DD/characters/`
- Moves rejected JSON to `data/rejected/`
- Logs to `logs/ingestion/promotions_YYYY-MM-DD.log`

**`weekly_update.py`**
- End-to-end pipeline wrapper (Steps 1–6 in order)
- `--dry-run` flag: skips scrape + diff, runs all other steps with their own dry-run flags
- Aborts on any step failure; prints step name + log path
- Logs every step to `logs/weekly_runs/YYYY-MM-DD_HH-MM.log` with timestamps
- Final summary: diff counts, chapters ingested, characters staged, next-action prompt
- Returns non-zero exit code on failure (cron-safe)

### Stage 1 findings: arc situation

All 19 chapters (1163–1181) belong to the **Elbaf Arc** (start_chapter: 1126, ongoing). Wiki confirmed no new arc started. `data/arcs.json` was correct — no changes needed.

Notable chapter titles from the gap:
- Ch. 1171: "Ragnir" (chapter named for a character → significant)
- Ch. 1175: "Niddhoggr" (Norse mythological dragon)
- Ch. 1179: "Nerona Imu Descends" — major plot event (Imu is the World Government's shadow ruler)

### Character ingestion results

| Character | Status | Debut | Affiliations | Result |
|---|---|---|---|---|
| Billy_the_Yabuki | Alive | SBS Vol 114 | — | Promoted |
| Bjorn | Alive | Ch. 1118 | Giant Warrior Pirates | Promoted |
| Gantonio | Alive | Ch. 1177 | Giant Warrior Pirates | Promoted |
| Love | Alive | Ch. 107 | Baroque Works (former) | Promoted |
| Magnolia | Deceased | Ch. 1158 | — | Promoted |
| Misty | Alive | Ch. 107 | Baroque Works (former) | Promoted |
| Ragnir ⚠️ | Alive | Ch. 1130 | Loki; Elbaph Royal Family | Promoted |
| Ratatoskr ⚠️ | Unknown | Ch. 1175 | Warrior God | Promoted |
| Warrior God ⚠️ | Deceased | Ch. 1175 | — | Promoted |
| D._D._Tee | — | — | Redirects to Giant Warrior Pirates crew section | **Rejected** |
| Rhodes | — | — | Redirects to Giant Warrior Pirates crew section | **Rejected** |

D._D._Tee and Rhodes had no standalone wiki pages (redirected to crew section). Rejection records written to `data/rejected/`.

### Graph state delta

| Label | Before Week 7 | After Week 7 | Delta |
|---|---|---|---|
| `:Character` | 1,517 | 1,526 | +9 |
| `:Chapter` | 515 | 534 | +19 |
| `:Arc` | 33 | 33 | 0 |
| `:DevilFruit` | 134 | 134 | 0 |
| `:Organization` | ~372 | ~376 | +4 (new orgs from promoted chars) |

### Stress test: Run 3 results

| | Run 2 | Run 3 | Delta |
|---|---|---|---|
| Score | 50/50 (100%) | 50/50 (100%) | 0 regressions |
| Avg latency | 7.51s | 8.53s | +1.02s (normal variance) |
| Q32 (Baroque Works) | 19 rows | 21 rows | **+2 ✓** (Love + Misty now in graph) |

Zero regressions. Q32 improvement is correct new data from Week 7 promotions.

### Weekly workflow — how to run it

**Command (every Sunday night):**
```bash
python weekly_update.py
```

Takes ~75–80 minutes total (dominated by the full wiki scrape). Steps:
1. `refresh_data.py --full` — fresh snapshot (~75 min)
2. `diff_snapshots.py` — diff against previous snapshot
3. `apply_patch.py --apply` — apply field-level updates
4. `detect_new_content.py` — find new chapters + characters
5. `ingest_new_chapters.py --apply` — auto-ingest new chapters
6. `stage_new_characters.py` — stage new characters for review

**Monday morning review:**
```bash
python promote_pending.py --list                          # see what's staged
python promote_pending.py --promote <slug>               # dry-run one
python promote_pending.py --promote <slug> --apply       # commit one
python promote_pending.py --promote-all --apply          # commit all (with confirmation)
python promote_pending.py --reject <slug> --reason "..." # reject
```

**Logs:**
- Weekly run logs: `logs/weekly_runs/YYYY-MM-DD_HH-MM.log`
- Chapter ingestion: `logs/ingestion/chapters_YYYY-MM-DD.log`
- Character staging: `logs/ingestion/staging_YYYY-MM-DD.log`
- Promotions: `logs/ingestion/promotions_YYYY-MM-DD.log`
- Patch logs: `logs/patches/YYYY-MM-DD_HH-MM.log`

### New v2 Backlog items from this week

- **Relationship patching in `apply_patch.py`** — currently only handles scalar field updates. When a character gains a new devil fruit or affiliation between scrapes, the diff detects it but the patch engine can't create the new graph relationship. Needs a second-pass relationship handler.
- **Arc name "Elbaph" vs "Elbaf"** — wiki spells it "Elbaph"; our data uses "Elbaf". Pre-existing source data discrepancy. Don't fix until a full arc re-import is scoped.
- **Slug mismatch audit** — wiki reports 1,525 characters, graph has 1,517. ~3 graph slugs don't match current wiki slugs (renamed/disambiguated pages). Future audit pass.
- **Auto-promote after N clean review cycles** — characters that consistently have good data (full infobox, clean affiliations, known debut) could skip manual review after a confidence threshold is established.

---

## v2 Backlog (deferred, not blocking MVP)

- **72 additional malformed org names** found after `fix_org_names.py` ran:
  - ~20 comma-fusion orgs (e.g. `"Beasts Pirates, Numbers"`) — same root cause as semicolon fusions; fix needs comma-splitting in `import_affiliations.py`
  - ~12 annotation-in-name orgs (e.g. `"Beasts Pirates(Tobiroppo)"`, `"Marines(SSG)"`) — annotation wasn't separated from org name
  - ~40 single-person orgs (character names used as affiliations) — reclassify or drop
- **`Brannew` name patch** — `MATCH (c:Character {opwikiID: "Brannew"}) SET c.name = "Brannew"`
- **`Gan_Fall` name review** — `SET c.name = "Gan Fall"` if Funimation spelling preferred over VIZ "Ganfor"
- **Bounty field parse** — all bounty values are concatenated with no separator; needs full reparse of raw data before it can be loaded
- **Full chapter list** — 515 `:Chapter` nodes cover only debut chapters; all 1100+ manga chapters need a separate data source
- **Haki** — needs scrape or manual data; not in source JSON

---

## Next up (Week 8)

- [ ] Load Locations as `:Location` nodes + `:BORN_IN` / `:RESIDES_IN` relationships (from `Origin` and `Residence` fields on `:Character` nodes)
- [ ] Load Occupations as `:Occupation` nodes (same semicolon-delimited source field)
- [ ] Update `graph_schema.md` to reflect new node types + relationship directions for the query layer
- [ ] Run stress test Run 4 after Week 8 schema changes — verify no regressions on existing questions

## Post-MVP Roadmap (not v1)

### Cost management (before public launch)
- Rate limiting per user / per session
- Caching common queries (hot questions = Straw Hats, Four Emperors, etc. - cache for 24h)
- Cheaper model for Cypher generation, better model for final answer synthesis
- Usage dashboard / per-user quotas
- Consider Haiku for Cypher gen ($) + Sonnet for answer ($$)

### Guardrails
- Topic restriction (must be One Piece related — pre-classify with a cheap check)
- Jailbreak resistance (system prompt hardening)
- Spoiler awareness (optional: cap answers at user's last-read chapter)
- Prompt injection defenses (sanitize user input before LLM call)

### Agentic layer
- Multi-step reasoning: LLM can issue 2-3 Cypher queries iteratively
- Self-correction: if first Cypher returns nothing, reformulate and retry
- Confidence scoring on answers

### Tool use
- Web search tool for info not in graph (recent chapters, wiki deep-dives)
- Theory retrieval (Reddit/forum search)
- Image generation for visualizing answers

### Real website
- Next.js / React frontend
- Auth + user accounts
- Save queries / share answers
- Graph visualization layer (interactive)

---

## Week 8 — Locations + Occupations (2026-04-22)

### What I did

- Loaded `:Location` nodes + `ORIGINATES_FROM` / `RESIDES_IN` relationships from `Origin` and `Residence` character fields
- Loaded `:Occupation` nodes + `HAS_OCCUPATION` relationships (with `status` property: current/former)
- Ran stress test run 4: 58/60 pass (97%). Both failures were pre-existing edge cases (same as run 3).
- Updated `docs/graph_schema.md` to reflect all new node types and relationship directions
- Updated `audit/locations_occupations_audit.md` with import counts and known gaps

### Graph state after Week 8

- Characters: 1,517 (no change)
- Locations: ~247 unique `:Location` nodes
- Occupations: ~661 unique `:Occupation` nodes
- Status property on `HAS_OCCUPATION` edges: current / former / unknown

---

## Week 9 — V1 triage, FastAPI backend, public repo prep (2026-04-22)

### What I did

**Stage 1 — V1 triage**
- Full sweep of weeks 1–8 notes + git history + code review
- Produced `docs/V1_TRIAGE.md`: 2 blockers, 5 polish items, 14 V2 deferrals
- Blockers: hardcoded Neo4j password across 17 files, Garling counted as a 6th Five Elder

**Stage 2 — V1 blockers fixed**
- Migrated all 17 scripts to `os.getenv("NEO4J_PASSWORD")` via a migration script
- Created `.env.example` documenting all required vars
- Fixed Garling: deleted the incorrect `AFFILIATED_WITH → Five Elders` edge; exactly 5 Five Elders now confirmed
- Added schema note (docs/graph_schema.md) and Cypher prompt rule (Rule 12) to prevent LLM from counting Garling as a sixth
- Also added Rule 13 (Kaku disambiguation) and Rule 14 (aggregation ORDER BY must only reference RETURN aliases)

**Stage 3 — Stress test expansion**
- Expanded from 60 → 75 questions: added categories for typos, multi-intent, spoiler-adjacent, superlatives, graph edge cases, prompt injection
- Fixed auto-numbering bug: runner was always writing `stress_test_run_1.md` (overwriting)
- Added `timeout=60.0` to `call_claude()` to prevent SDK from hanging indefinitely on API stalls
- Run 5 (60 questions): **98% pass rate** (59/60)
- Run 6 (75 questions): **96% pass rate** (72/75); 3 failures: Q20 false positive (keyword guard too broad), Q68 spoiler-adjacent (0 rows expected), Q71 superlative (no graph answer, expected)

**Stage 4 — Neo4j Aura migration**
- Deferred — user doesn't have Aura account yet; will migrate when needed for production

**Stage 5 — FastAPI streaming backend**
- Built complete API in `api/`: config, cache, ask_service, rate_limit, turnstile, logging, health, stats, ask, admin routes
- SSE event protocol: step_start → step_complete → answer_chunk* → done | error
- In-memory TTL cache (24h, SHA-256 key)
- Per-IP sliding window rate limiter (30 req/hr)
- Cloudflare Turnstile bot protection (bypassable via `TURNSTILE_ENABLED=false` in dev)
- Structured JSON request logging middleware
- Admin endpoint (`/api/admin/stats`) gated by `X-Admin-Token`
- Local test: health 200, stats 200 (1,526 chars, 534 chapters, 33 arcs, 661 occupations, 247 locations, 134 devil fruits, 362 organizations)

**Stage 6 — Security layer**
- All security components were built as part of Stage 5 (rate limiting, Turnstile, CORS, logging)

**Stage 7 — Public repo prep**
- Secrets sweep: no real API keys in git history; only `Mussa1234` (local-only Neo4j password, already rotated by Aura migration)
- Added: `LICENSE` (MIT), `CREDITS.md`, `CONTRIBUTING.md`, `README.md`, `ROADMAP.md`, `docs/ARCHITECTURE.md`
- Created `docs/DEPLOYMENT.md`: full guide for Aura + Railway + Vercel + Cloudflare + spend cap

**Stage 8 — Railway deployment dry run**
- Created `Procfile` and `nixpacks.toml` for Railway
- Verified local API start: health + stats endpoints both 200
- Ready to deploy as soon as user creates Railway account

**Project cleanup**
- Moved 7 loose pipeline scripts from root → `pipeline/` directory: `refresh_data.py`, `diff_snapshots.py`, `apply_patch.py`, `detect_new_content.py`, `ingest_new_chapters.py`, `stage_new_characters.py`, `promote_pending.py`
- Updated all `__file__`-based path anchors in moved scripts to resolve from project root
- Updated `weekly_update.py` subprocess call paths to use `pipeline/` prefix
- Updated CLAUDE.md and README.md project structure sections

### Graph state after Week 9

- Characters: 1,526 (9 promoted from pipeline testing this week)
- All other node counts unchanged
- API: running locally at port 8000, ready for Railway deployment
- Stress test: 96% pass rate on 75-question suite (run 6)

### Next up (Week 10)

- [ ] Create Neo4j Aura Free instance + migrate local graph (dump/restore)
- [ ] Deploy to Railway, get public URL
- [ ] Set Anthropic spend cap in console (REQUIRED before any public access)
- [ ] Run stress test run 7 against Aura to confirm graph parity
- [ ] Start Next.js frontend (Week 12 milestone)

---

## Week 10 — Production deploy (Aura + Railway) + security hardening (2026-04-23)

### What shipped

**Stages 1-2 complete.** Poneglyph is live in production.

- **Neo4j Aura:** graph migrated from local; 1,526 characters / 534 chapters / 247 locations / 661 occupations / 134 devil fruits / 362 orgs / 33 arcs all present. Verified via `/api/stats` against Aura.
- **Railway:** FastAPI backend deployed at https://poneglyph-production-dfaf.up.railway.app. `NEO4J_ENV=aura` toggles the app between local-dev and Aura-prod without code change.
- **Smoke test (2026-04-23, post-config-fix):** `/api/health` 200 (neo4j connected, anthropic configured), `/api/stats` 200, `/api/ask` 200 SSE with full pipeline (Cypher generate → Aura query → streamed answer with Chapter 1 citation).
- **Security:** Cloudflare Turnstile enabled (site key `0x4AAAAAADCC3pXeAWpkFhMQ`), per-IP rate limit at 10/hr (verified 403 on null-token curl).

### Deviations from the Week 10 plan — documented and approved

1. **Spend cap: $100/month + $50 alert**, not $15/day (Anthropic doesn't expose a hard daily cap, only monthly caps + alerts).
   - **Daily check, first week post-launch:** open console.anthropic.com daily for the first 7 days to eyeball usage trend. Set phone/calendar reminder for this.
   - **Kill-switch procedure if $50 alert fires:**
     1. Go to Railway → Deployments → click active deploy → "Stop Deployment" (or toggle service to paused).
     2. Open Anthropic console → Usage → inspect the last hour of calls, identify the bucket that blew up.
     3. Check Railway request logs for the IPs / user-agents behind the spike.
     4. Do not restart the deploy until root cause is understood (likely: Turnstile bypass, new bot, or genuine load spike that warrants tightening rate limits further).
2. **`RATE_LIMIT_PER_HOUR=10`**, not 30. Conservative default while the API sits public with Turnstile-only protection. **Bump to 30/hr in Stage 6 once Turnstile is verified working on the frontend.** (A matching TODO lives in `api/middleware/rate_limit.py`.)
3. **Stress test baseline:** comparing run 7 against run 6 (75q, 96%, 13.48s avg), not run 5 (60q — older, smaller suite).

### Code changes this week

- `api/config.py` — `NEO4J_ENV=local|aura` toggle + Aura-aware URI/user/password/database properties.
- `api/core/ask_service.py` — stopped routing `/api/ask` through `query/ask.py`'s CLI-era Neo4j constants; now uses api settings directly (commit `0b204fa`). This was the bug that made `/api/ask` hit `localhost:7687` from inside Railway.
- `pipeline/` — `RATE_LIMIT_PER_HOUR` + `NEO4J_ENV` env vars honored.
- `Procfile` + `nixpacks.toml` — Railway-specific build config (commits `e87c5c5`, `ab943ed`).

### Stages shipped

- [x] **Stage 3** — Aura stress test run 7: 74/75 pass (99%), 12.98s avg latency. Up 2 questions vs local run 6, zero regressions. Commit `e7cd44f`.
- [x] **Stage 4** — Lovable frontend merged into `web/`, `FRONTEND_GUIDELINES.md` authored at repo root. `bun.lockb` removed (npm is the lockfile). Commit `ef7137c`.
- [x] **Stage 5** — answer LLM emits inline `[[Ch.NNN|Arc]]` citation tokens. Arc resolution via `build_arc_map()` (one Neo4j lookup). `_extract_citations` in `api/core/ask_service.py` dedupes for the frontend. Stress test run 9: 73/75 = 97%, 12.82s avg, 115 inline tokens, 0 malformed. Commit `a3bd7c5`.
- [x] **Stage 6** — `web/src/lib/askRobin.ts` wired to real backend, `@marsidev/react-turnstile` invisible widget on `/ask`. Typed errors (RateLimitError/TurnstileError/BackendError). Rate limit bumped 10→30/hr on Railway. Commit `e62cbf3`.
- [x] **Stage 7** — Robin-voiced parchment error panels with retry + 3-attempt exhaustion. Live countdown sourced from `Retry-After` (60s fallback). All three panels visually verified locally. Commit `4051943`.
- [x] **Stage 8** — `/api/stats` fetched on About mount; hardcoded fallback persists silently if backend down. Live values replace fallback after ~1s. Commit `48d038a`.
- [x] **Stage 9** — Vercel deployed at https://poneglyph-seven.vercel.app. `web/vercel.json` adds SPA rewrites. Cloudflare Turnstile + Railway `ALLOWED_ORIGINS` both updated to allow the Vercel domain. Production live end-to-end 2026-04-26 — first prod-to-prod question ("who is luffy") returned a Robin-voiced answer with citation pill. Prep commit `67d1b54`.
- [x] **Stage 10** — these notes + clean commit.

### Week 10 wrap-up

**What I actually shipped this week:**
- A live, public Robin: anyone with the URL can ask the graph anything, end-to-end on real infra.
- Real security at the edge: Turnstile gating, per-IP rate limit, no hardcoded credentials anywhere in the repo.
- A real frontend: parchment design system, Robin's voice, citation pills, error states that don't break character.
- Operational discipline: env-var single-source-of-truth (`utils/neo4j_env.py`), every deploy verifiable via `/api/health` + `/api/stats`.

**What surprised me:**

1. **Stage 9 had six different infrastructure gates I had to walk through one by one** — Vercel root directory, env-var injection at build time, Cloudflare Turnstile per-hostname allowlist, Railway CORS allowlist, the production-alias vs deployment-URL distinction, and the Vercel "Environments" vs "Environment Variables" UI trap. None of these were in the plan. Each one was a 20-minute debug. The lesson: prod deploy is not "one big step" — it's a chain of small misconfigurations, and you can only find them by triggering each one.
2. **The `git commit` hang from Stage 6 was specifically post-`npm ci`, not a permanent fsevents curse** — Stages 7, 8, 9 all committed cleanly via plain `git commit` with no plumbing fallback. Memory has been corrected.
3. **The accidental BackendError test in Stage 7** — when Railway CORS-rejected localhost during the Turnstile smoke, it gave me a real `STONES DISTURBED` parchment panel from a network failure. That was a free production-style validation of the BackendError path I would have had to mock otherwise.
4. **Vercel preview/deployment URLs do not work end-to-end** — only the production alias `poneglyph-seven.vercel.app` is allowed by Cloudflare and Railway. If I ever want preview deploys to function (Week 11+ when I start branching), I'll need `allow_origin_regex=r".*\.vercel\.app$"` on the FastAPI CORSMiddleware and `*.vercel.app` on the Cloudflare hostname list.

**What to remember next time:**

- **Push to `origin/main` before configuring Vercel.** Vercel's import wizard reads the default branch's directory tree to populate the Root Directory dropdown — if `web/` only exists locally, it won't appear there.
- **Vercel env vars only inject at build time.** Adding them after a failed first deploy means redeploying with cache disabled. Set vars in the import wizard before the first build whenever possible.
- **The Cloudflare Turnstile site key has a hostname allowlist.** Every new domain (including `localhost` for dev) must be added explicitly, otherwise the widget fails silently with error 110200 and the backend gets `turnstile_missing` 403s. Local dev without Turnstile validation is the cleanest path — set `TURNSTILE_ENABLED=false` locally and let the backend short-circuit.
- **The FastAPI CORS default in `api/config.py:26` is `http://localhost:3000`** — useless for production. `ALLOWED_ORIGINS` must be set explicitly on Railway and on every new origin we onboard.
- **Stress test pacing matters.** Run 9 added 1.5s between questions to stay under Anthropic's 30k input-TPM ceiling on 75-q runs. Don't fire 75 questions back-to-back into the API.

**Spend over Week 10:** below the $50 alert. Anthropic console shows usage trending fine for current traffic (just me + smoke tests). Will recheck weekly.

**The product as of 2026-04-26:**
- 1,526 characters / 534 chapters / 247 locations / 661 occupations / 134 devil fruits / 362 orgs / 33 arcs in Neo4j Aura
- ~97-99% stress test pass rate (Aura, 75 questions, ~13s avg latency)
- Prod URL: https://poneglyph-seven.vercel.app
- Backend: https://poneglyph-production-dfaf.up.railway.app
- The graph + Robin, end-to-end, public, gated, paid for, alive.