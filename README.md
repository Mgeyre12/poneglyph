# Poneglyph

A One Piece knowledge graph with a natural-language query layer. Ask lore questions in plain English, get chapter-grounded answers.

```
"Who are the Five Elders?"
→ Saturn, Mars, Nusjuro, Ju Peter, Warcury — all five confirmed with debut chapters.

"Which characters have eaten two devil fruits?"
→ Blackbeard is the only confirmed case (Yami Yami no Mi + Gura Gura no Mi, Ch 577).

"What former Marines became pirates?"
→ Returns matching characters with affiliation history and debut chapters.
```

Named after the indestructible stones in One Piece that contain encoded world history — readable only by those who know the ancient language. The graph is the stone. The LLM is Robin.

---

## What it is

- **1,526 `:Character` nodes** covering the full One Piece roster through Chapter 1181
- **Relationships:** affiliations, occupations, locations, devil fruit users, arc debuts
- **Query layer:** natural-language question → Cypher generation (Claude) → Neo4j → grounded answer (Claude, streaming)
- **API:** FastAPI backend with SSE streaming, per-IP rate limiting, Cloudflare Turnstile bot protection

---

## Stack

| Layer | Technology |
|---|---|
| Graph | Neo4j (local) / Neo4j Aura Free (prod) |
| Ingestion | Python 3.11 + MediaWiki API scraper |
| Query | Anthropic Claude (claude-sonnet-4-6) |
| API | FastAPI + uvicorn, Server-Sent Events |
| Frontend | Next.js on Vercel (Week 12) |
| Hosting | Railway (API) + Neo4j Aura Free |

---

## Quick start (local)

**Prerequisites:** Neo4j Desktop running at `bolt://localhost:7687` with a database started.

```bash
git clone https://github.com/Mgeyre12/poneglyph
cd poneglyph

pip install -r requirements.txt
pip install -r api/requirements.txt

cp .env.example .env
# Fill in NEO4J_PASSWORD and ANTHROPIC_API_KEY
```

**Load the graph (one-time):**

```bash
python3 ingest/import_characters.py
python3 ingest/import_devil_fruits.py
python3 ingest/import_affiliations.py
python3 ingest/import_arcs.py
python3 ingest/import_chapters.py
python3 import_locations.py
python3 import_occupations.py
```

**Ask a question:**

```bash
python query/ask.py "who are the straw hats?"
```

**Run the API:**

```bash
uvicorn api.main:app --reload
# POST http://localhost:8000/api/ask  {"question": "who are the straw hats?"}
```

---

## Project structure

```
poneglyph/
├── api/              # FastAPI backend (routes, middleware, core services)
├── ingest/           # import_*.py — load data into Neo4j
├── pipeline/         # refresh, diff, patch, detect, ingest, stage, promote
├── query/            # ask.py — CLI query layer
├── fixes/            # fix_*.py — normalization and cleanup scripts
├── utils/            # generate_schema.py and other utilities
├── docs/             # Architecture, schema, deployment guides
├── data/             # Raw/processed JSON source files + snapshots
├── diff/             # Field-level diff reports
├── reports/          # Pending character/chapter detection reports
├── audit/            # Data quality audits
├── tests/            # 75-question stress test suite
└── logs/             # Ingestion logs, patch logs, weekly run logs
```

---

## Keeping the graph current

The scraper pulls from the One Piece Wiki via the MediaWiki API. The weekly workflow:

```bash
python weekly_update.py                 # full pipeline dry-run (safe)

python pipeline/refresh_data.py --full  # re-scrape all 1,517 characters (~75 min)
python pipeline/diff_snapshots.py data/snapshots/baseline data/snapshots/YYYY-MM-DD
python pipeline/apply_patch.py --dry-run diff/YYYY-MM-DD_diff.json
python pipeline/apply_patch.py --apply  diff/YYYY-MM-DD_diff.json
python pipeline/detect_new_content.py   # report new chapters/characters
```

---

## Testing

```bash
# 75-question stress test (requires Neo4j + Anthropic API key, ~$0.10-0.20)
python tests/run_stress_test.py

# Latest result: 98% pass rate (run 5, 2026-04-22)
```

---

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full guide: Neo4j Aura, Cloudflare Turnstile, Railway, Vercel, and spend cap setup.

---

## Credits

Data sourced from [kalnassag/one-piece-ontology](https://github.com/kalnassag/one-piece-ontology) (MIT) and the [One Piece Wiki](https://onepiece.fandom.com/wiki/One_Piece_Wiki). See [CREDITS.md](CREDITS.md).

One Piece is created by Eiichiro Oda. This is a fan project — not affiliated with or endorsed by Oda, Shueisha, or Toei.

---

## License

MIT — see [LICENSE](LICENSE).
