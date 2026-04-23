# Roadmap

## V1 — current scope

The goal for V1 is a publicly accessible, lore-accurate query layer over the full One Piece character graph. All items below are complete or in-flight.

### Done
- [x] 1,526 `:Character` nodes (full roster through Ch 1181)
- [x] `:DevilFruit` nodes + `ATE` / `PREVIOUSLY_ATE` relationships
- [x] `:Affiliation` / `:Organization` nodes + `AFFILIATED_WITH` relationships
- [x] `:Arc` nodes + `DEBUTED_IN` relationships
- [x] `:Location` nodes + `ORIGINATES_FROM` / `RESIDES_IN` relationships
- [x] `:Occupation` nodes + `HAS_OCCUPATION` relationships
- [x] Weekly refresh pipeline (scrape → diff → patch → detect)
- [x] Natural-language query layer (Claude Cypher generation + answer synthesis)
- [x] FastAPI backend with SSE streaming, in-memory cache, rate limiting
- [x] Cloudflare Turnstile bot protection
- [x] Structured JSON request logging
- [x] 75-question stress test suite (latest: 98% pass rate)
- [x] Neo4j Aura Free migration (cloud graph)
- [x] Public repo prep (LICENSE, CREDITS, CONTRIBUTING, secrets sweep)

### In progress
- [ ] Railway deployment (FastAPI API)
- [ ] Next.js frontend (Week 12)
- [ ] Vercel deployment

---

## V2 — backlog

These are real improvements that were intentionally deferred — either because the data isn't clean enough yet, the value doesn't justify the complexity, or they belong in a separate agentic layer.

### Data quality
- **Bounty field parse** — source data concatenates multiple bounty values with no separator; needs a full re-scrape with a dedicated parser
- **Haki data** — not in the source JSON; requires manual curation or a new wiki scrape target
- **Age variants** — debut / pre-timeskip / current ages are available in raw strings; structured multi-value would enable "who was youngest at debut?" queries
- **Birthday date parsing** — raw strings are human-readable; ISO dates would enable birthday-range queries
- **72 malformed org names** — ~40 are single-person pseudo-orgs (e.g. "The King of the Pirates"), ~20 are comma-fusion artifacts from scraping; fixing without data errors requires a new pass
- **Full chapter list** — the graph has debut chapters but not the full chapter-to-arc index; filling the gaps needs a new data source or manual curation
- **Slug mismatch audit** — ~3 wiki slugs differ from graph keys; low query impact but worth a clean pass

### Query improvements
- **Multi-step Cypher reasoning** — for questions that require chained lookups ("who trained the person who trained X?"), the current single-Cypher-per-question design hits a ceiling; agentic multi-step would handle these
- **Web search tool** — for out-of-graph facts ("what is the Laugh Tale?"), a fallback search tool would prevent dead-end "not in graph" answers
- **Answer LLM training data leaks** — the answer synthesis model occasionally responds with anime-only or filler content; prompt hardening is a deeper prompt-engineering project

### Pipeline automation
- **Auto-promote characters after N clean cycles** — characters in `pending_review/` that pass scraping cleanly for 3 consecutive weeks should auto-promote without manual review
- **Relationship patching in apply_patch.py** — the current patcher is scalar-only; relationship field changes (affiliation status updates) require a separate pass with duplicate-guard logic

### Disambiguation and edge cases
- **Kaku CP9 / Kaku Wano (full fix)** — two characters share the name "Kaku"; current prompt rule handles disambiguation adequately, but a graph-level `displayName` distinction would be cleaner
- **Garling / Five Elders (graph-level fix)** — Garling has an `AFFILIATED_WITH → Five Elders` edge that is technically correct but misleads aggregate queries; a `role` property on the relationship would be the right fix
- **Arc name normalization** — minor discrepancies between arc names in data vs. wiki (e.g. "Elbaf Arc" vs. "Elbaf")
