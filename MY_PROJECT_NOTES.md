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

## Known issues to address later

- `height_cm` for Luffy is `91` (should be `174`) — scraping bug in the source data, the wiki listed the value in a format the scraper misread. Fix: manually patch known wrong heights, or re-scrape with a corrected parser.
- `Age` field in the source JSON is a multi-value string (e.g. `"7 (debut);17 (pre-timeskip);19 (post-timeskip)"`). The import script takes the last value. Pre-timeskip ages are lost — consider storing all three as separate properties (`age_debut`, `age_pretimeskip`, `age_current`) in a future pass.
- `Bounty` field in source JSON is all values concatenated with no separator — unusable as-is. Needs a full reparse against the raw data before it can be loaded.
- 185 characters have no `Official English Name` — `name` falls back to Romanized Name for these.
- Two `:Character` nodes have `status: "Destroyed"` or `status: "Active"` — likely non-human entities (a ship, a weapon) that ended up in the character list. Worth filtering or reclassifying.
- `Birthday` is stored as a raw string (`"May 5th (Children's Day)"`). Should be parsed to a proper date in a future pass.

---

## What's next (Day 2+)

- [ ] Add relationships: `:AFFILIATED_WITH`, `:HAS_OCCUPATION` from the semicolon-delimited fields
- [ ] Load Devil Fruits as `:DevilFruit` nodes and connect to characters
- [ ] Load Locations and connect via `:BORN_IN`, `:RESIDES_IN`
- [ ] Add canonicity tier property to nodes
- [ ] Start LLM query layer (text-to-Cypher)
