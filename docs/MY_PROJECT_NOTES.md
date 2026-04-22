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

## Next up

- [ ] Load Occupations as `:Occupation` nodes (same semicolon-delimited source field)
- [ ] Load Locations as `:Location` nodes + `:BORN_IN` / `:RESIDES_IN` relationships
- [ ] Build re-scrape / graph update pipeline — diff new scrape against current graph, patch only changed nodes (first use case: Imu's fruit)
- [ ] Improve Five Elders query — add `rank` or `role` property to `:AFFILIATED_WITH` so Garling doesn't appear as an Elder
- [ ] Prompt improvement pass using `failure_cases.md` once more failures accumulate

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