# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Poneglyph** — One Piece knowledge graph with a natural-language LLM query layer. Data lives in Neo4j; Python scripts handle ingestion. Long-term goal: fans can query lore, track foreshadowing, and validate theories with chapter-grounded answers.

Named after the indestructible stones in One Piece that contain encoded world history — readable only by those who know the ancient language. Here, the graph is the stone and the LLM is Robin.

Data sourced from [kalnassag/one-piece-ontology](https://github.com/kalnassag/one-piece-ontology) (MIT). The raw/processed JSON files in `data/` came from that fork — do not overwrite them without re-running the upstream scraper.

## Neo4j connection

- **URL:** `bolt://localhost:7687`
- **User:** `neo4j`
- **Password:** stored in `NEO4J_PASSWORD` constant at the top of each script — currently `Mussa1234`
- **Browser:** `http://localhost:7474`
- **Database must be started manually** in Neo4j Desktop before running any script.

## Project structure

```
poneglyph/
├── ingest/       # import_*.py — load data into Neo4j
├── fixes/        # fix_*.py — normalization and cleanup scripts
├── query/        # ask.py — natural-language LLM query layer
├── utils/        # generate_schema.py and other utilities
├── docs/         # graph_schema.md, test_queries.md, MY_PROJECT_NOTES.md
├── data/         # raw/processed JSON source files
└── logs/         # per-run skip/error logs
```

## Running import scripts

```bash
pip install neo4j
python3 ingest/import_characters.py
```

All import scripts are idempotent — safe to re-run. They use `MERGE` keyed on `opwikiID` and create a uniqueness constraint on first run.

## Graph schema (current state)

**Nodes:**
- `:Character` — 1,517 nodes, keyed on `opwikiID` (wiki URL slug, e.g. `"Monkey_D._Luffy"`)

**Constraints:**
- `character_id`: `opwikiID IS UNIQUE` on `:Character`

**Not yet loaded** (planned): `:DevilFruit`, `:Location`, `:Affiliation`, `:Occupation` nodes and their relationships.

## Data files

| File | Contents |
|---|---|
| `data/full-character-data-processed-2.json` | 1,517 characters, processed (citation tags stripped, `debut_chapter` and `height_cm` derived) |
| `data/devil_fruits.json` | 134 devil fruits with type, debut, current/previous users |

Key data quirks to know before writing new import logic:
- `Affiliations` and `Occupations` are semicolon-delimited strings, not arrays — split on `;` and strip parenthetical suffixes like `(former)` before creating relationship targets.
- `Age` is a multi-value string (`"7 (debut);17 (pre-timeskip);19 (post-timeskip)"`) — last segment is current age.
- `height_cm` is a string, not a number — needs `float()` conversion. Some values are wrong (Luffy is `91` instead of `174`) due to upstream scraping bugs.
- `Bounty` values are concatenated with no separator — not yet usable.
- 185 characters have no `Official English Name` — fall back to `Romanized Name` then `source_name`.

## Adding new import scripts

Follow the pattern in `ingest/import_characters.py`:
1. Constants block at the top (URI, USER, PASSWORD, DATA_FILE)
2. Pure helper functions for parsing/cleaning individual fields
3. `build_node_props(record)` → clean dict with `None` values stripped before writing
4. `run_import(driver, records)` → creates constraints, loops with per-record try/except, prints progress every 100 records
5. `main()` → opens file, connects, calls run_import, closes driver
