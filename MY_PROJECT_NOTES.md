# One Piece Knowledge Graph — Project Notes

A One Piece knowledge graph + natural-language LLM query layer for fans.
Track foreshadowing, validate theories, get grounded answers with chapter citations.

**Stack:** Neo4j (graph DB) + Python + LLM query layer (coming later)
**Data source:** Forked from [kalnassag/one-piece-ontology](https://github.com/kalnassag/one-piece-ontology)
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

## Next up

- [ ] Clean up multi-value `name` fields on `:Character` nodes (parse out a single canonical name)
- [ ] Patch malformed org `"Whitebeard Pirates2nd Division"`
- [ ] Load Locations as `:Location` nodes + `:BORN_IN` / `:RESIDES_IN` relationships
- [ ] Load Occupations as `:Occupation` nodes (same semicolon-delimited source field)
- [ ] Build text-to-Cypher LLM query layer
- [ ] Full chapter list as `:Chapter` nodes (needs a separate data source beyond debut chapters)
- [ ] Add Haki as a character property or node (needs scrape/manual data)
- [ ] Parse `Bounty` field (currently concatenated with no separator — needs reparse)
