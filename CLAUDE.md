# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Poneglyph** — One Piece knowledge graph with a natural-language LLM query layer. Data lives in Neo4j; Python scripts handle ingestion. Long-term goal: fans can query lore, track foreshadowing, and validate theories with chapter-grounded answers.

Named after the indestructible stones in One Piece that contain encoded world history — readable only by those who know the ancient language. Here, the graph is the stone and the LLM is Robin.

Data sourced from [kalnassag/one-piece-ontology](https://github.com/kalnassag/one-piece-ontology) (MIT). The raw/processed JSON files in `data/` came from that fork — do not overwrite them without re-running the upstream scraper.

## Neo4j connection

- **URL:** `bolt://localhost:7687` (override with `NEO4J_URI` env var)
- **User:** `neo4j` (override with `NEO4J_USER`)
- **Password:** set in `.env` as `NEO4J_PASSWORD` — never hardcoded
- **Browser:** `http://localhost:7474`
- **Database must be started manually** in Neo4j Desktop before running any script.
- Copy `.env.example` → `.env` and fill in credentials before running anything.

## Project structure

```
poneglyph/
├── api/              # FastAPI backend (routes, middleware, core services)
├── ingest/           # import_*.py — load data into Neo4j
├── pipeline/         # refresh, diff, patch, detect, ingest, stage, promote scripts
├── fixes/            # fix_*.py — normalization and cleanup scripts
├── query/            # ask.py — natural-language LLM query layer
├── utils/            # generate_schema.py and other utilities
├── docs/             # graph_schema.md, ARCHITECTURE.md, DEPLOYMENT.md, etc.
├── data/snapshots/   # timestamped per-character scrape snapshots
├── diff/             # field-level diff reports (md + json)
├── reports/          # pending_updates detection reports
├── audit/            # scraper audit, missing character investigation
├── tests/            # stress test suite and runner
├── data/             # raw/processed JSON source files
└── logs/             # per-run skip/error logs + patch logs
```

## Refresh workflow (keeping the graph current)

```bash
python weekly_update.py                 # full pipeline dry-run (safe)
python weekly_update.py --dry-run       # explicit dry-run

python pipeline/refresh_data.py --test  # scrape 50-char test set
python pipeline/refresh_data.py --full  # scrape all 1,517 (~75 min)
python pipeline/diff_snapshots.py data/snapshots/baseline data/snapshots/YYYY-MM-DD
python pipeline/apply_patch.py --dry-run diff/YYYY-MM-DD_diff.json
python pipeline/apply_patch.py --apply   diff/YYYY-MM-DD_diff.json
python pipeline/detect_new_content.py   # report new chapters/characters
```

The scraper uses the MediaWiki API (`action=parse&prop=text`) — direct wiki requests return 403 since ~2025.

## Running import scripts

```bash
pip install neo4j
python3 ingest/import_characters.py
```

All import scripts are idempotent — safe to re-run. They use `MERGE` keyed on `opwikiID` and create a uniqueness constraint on first run.

## Graph schema (current state)

**Nodes:** `:Character` (1,526), `:DevilFruit` (134), `:Organization` (~600), `:Occupation` (~400), `:Location` (~800), `:Arc` (33), `:Chapter` (~200)

**Key relationships:** `AFFILIATED_WITH`, `HAS_OCCUPATION`, `ORIGINATES_FROM`, `RESIDES_IN`, `ATE_FRUIT`, `PREVIOUSLY_ATE`, `DEBUTED_IN`, `IN_ARC`

Full schema with known quirks: `docs/graph_schema.md`

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

## Frontend (`web/`)

The Vite + React + Tailwind + shadcn/ui frontend lives in `web/` (merged from the Lovable export in Week 10 Stage 4).

**Before editing anything under `web/`, read `FRONTEND_GUIDELINES.md` at the repo root.** It is the design contract — HSL tokens, surface classes, Robin's voice, the `askRobin` contract, and hard rules (no hardcoded colors, no emoji, no purple/neon, no Next.js, no toast popups for Robin errors).

```bash
cd web
npm install
npm run dev     # http://localhost:8080 (NOT 5173 — configured in vite.config.ts)
npm run build
npm run test
```

`src/lib/askRobin.ts` is a stub until Week 10 Stage 6. Its signature — `askRobin(q: string): Promise<RobinAnswer>` — is the contract the real backend wiring must satisfy. v1 is a blocking call; streaming display is Week 11.
