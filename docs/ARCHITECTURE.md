# Architecture

## Overview

Poneglyph is a four-layer system: data ingestion, graph storage, query service, and API/UI.

```
User question (natural language)
        │
        ▼
┌─────────────────────────────────┐
│         FastAPI (Railway)        │  Layer 4 — API
│  rate limit → cache check →     │
│  SSE stream back to client      │
└──────────────┬──────────────────┘
               │
        ▼  (cache miss)
┌─────────────────────────────────┐
│       Query Service              │  Layer 3 — LLM Query
│  ask.py / api/core/ask_service  │
│                                 │
│  1. Claude: question → Cypher   │
│  2. Neo4j: run Cypher           │
│  3. Claude: rows → answer (SSE) │
└──────────────┬──────────────────┘
               │
        ▼
┌─────────────────────────────────┐
│         Neo4j Graph              │  Layer 2 — Graph DB
│  1,526 Character nodes           │
│  Affiliations, Occupations,     │
│  Locations, Devil Fruits, Arcs  │
└──────────────┬──────────────────┘
               │
        ▼
┌─────────────────────────────────┐
│       Ingestion Pipeline         │  Layer 1 — Data
│  MediaWiki API → Python ingest  │
│  Weekly refresh + diff + patch  │
└─────────────────────────────────┘
```

---

## Layer 1 — Data ingestion

Source: One Piece Wiki (onepiece.fandom.com) via the MediaWiki API (`action=parse&prop=text`). Direct wiki requests return 403 since ~2025; the API does not.

**Initial load sequence:**

```bash
python3 ingest/import_characters.py     # 1,526 Character nodes
python3 ingest/import_devil_fruits.py   # 134 DevilFruit nodes + ATE edges
python3 ingest/import_affiliations.py   # Organization nodes + AFFILIATED_WITH edges
python3 ingest/import_arcs.py           # Arc nodes
python3 ingest/import_chapters.py       # Chapter nodes + IN_ARC edges + DEBUTED_IN edges
python3 import_locations.py             # Location nodes + ORIGINATES_FROM / RESIDES_IN
python3 import_occupations.py           # Occupation nodes + HAS_OCCUPATION edges
```

All scripts are idempotent (`MERGE` on `opwikiID`), dry-run by default, and require `--apply` to write.

**Weekly refresh:**

```
refresh_data.py --full          re-scrape all 1,517 characters (~75 min)
diff_snapshots.py               field-level diff: new / changed / removed
apply_patch.py --apply          write field changes to graph (scalar only)
detect_new_content.py           find new chapters + characters not yet in graph
stage_new_characters.py         scrape new characters into pending_review/
promote_pending.py              promote reviewed characters into graph
weekly_update.py                orchestrates the full pipeline
```

---

## Layer 2 — Graph schema

**Node types:**

| Label | Count | Key property |
|---|---|---|
| `:Character` | 1,526 | `opwikiID` |
| `:DevilFruit` | 134 | `fruit_id` |
| `:Organization` | ~600 | `name` |
| `:Occupation` | ~400 | `name` |
| `:Location` | ~800 | `name` |
| `:Arc` | 33 | `name` |
| `:Chapter` | ~200 | `number` |

**Relationship types:**

| Relationship | From → To | Key properties |
|---|---|---|
| `AFFILIATED_WITH` | Character → Organization | `status` (current/former/disbanded/…) |
| `HAS_OCCUPATION` | Character → Occupation | `status` |
| `ORIGINATES_FROM` | Character → Location | — |
| `RESIDES_IN` | Character → Location | — |
| `ATE_FRUIT` | Character → DevilFruit | — |
| `PREVIOUSLY_ATE` | Character → DevilFruit | — |
| `DEBUTED_IN` | Character → Chapter | — |
| `IN_ARC` | Chapter → Arc | — |

Full schema with known quirks and disambiguation notes: [graph_schema.md](graph_schema.md).

---

## Layer 3 — Query service

`query/ask.py` (CLI) and `api/core/ask_service.py` (async API) implement the same pipeline:

**Step 1: Cypher generation**

The question is sent to `claude-sonnet-4-6` with a system prompt containing:
- Full graph schema
- 14 Cypher rules (relationship names, property names, status values, aggregation constraints, Five Elders canonical list, Kaku disambiguation, etc.)
- 10 few-shot examples covering common query patterns

The model returns a Cypher query. The query is validated against a blocklist of destructive keywords before execution.

**Step 2: Graph query**

The Cypher is executed against Neo4j. Results are returned as a list of row dicts.

**Step 3: Answer synthesis**

The original question + Cypher + result rows are sent to `claude-sonnet-4-6` for answer synthesis. The model is instructed to:
- Ground every claim in the returned rows
- Cite debut chapters where available
- Say "the graph doesn't have that information" rather than hallucinating

In the CLI (`ask.py`), the answer is printed synchronously. In the API (`ask_service.py`), the answer is streamed via `client.messages.stream()` and emitted as SSE `answer_chunk` events.

**Caching:** SHA-256 of the question (lowercase, stripped) → 24h TTL. Cache is in-memory; a process restart clears it. Cache hits skip Steps 1–3 entirely.

---

## Layer 4 — API

`api/main.py` — FastAPI application.

**Request lifecycle for `POST /api/ask`:**

```
1. StructuredLoggingMiddleware — log request metadata as JSON
2. CORS check (ALLOWED_ORIGINS env var)
3. Rate limit check — 30 req/hr per IP (sliding window, in-memory)
4. Turnstile verification — if TURNSTILE_ENABLED=true, validate token
5. Cache lookup — return cached SSE stream if hit
6. ask_service.run_ask() — generate Cypher, run query, stream answer
7. StreamingResponse — emit SSE events to client
```

**SSE event protocol:**

```
event: step_start      {"step": "cypher_generation"}
event: step_complete   {"step": "cypher_generation", "cypher": "MATCH ..."}
event: step_start      {"step": "query_execution"}
event: step_complete   {"step": "query_execution", "rows": [...], "count": N}
event: answer_chunk    {"text": "..."}   (repeated, streaming)
event: done            {"citations": [...], "cached": false, "latency_ms": N}

# On error:
event: error           {"message": "...", "code": "cypher_failed"|"answer_generation_failed"|...}
```

**Other endpoints:**

| Endpoint | Auth | Description |
|---|---|---|
| `GET /api/health` | none | Version + timestamp |
| `GET /api/stats` | none | Graph node/rel counts (1h cache) |
| `GET /api/admin/stats` | `X-Admin-Token` header | Cache size, rate limiter state |

---

## Key design decisions

**Why SSE instead of WebSockets?** The ask flow is unidirectional (server → client) after the initial POST. SSE is simpler to implement, works over HTTP/1.1, and doesn't require connection management. The client can reconnect transparently.

**Why in-memory cache?** Aura Free has strict query limits. Caching identical questions eliminates redundant Cypher execution and Claude API calls. The 24h TTL balances freshness (the graph updates weekly) against API cost. An external cache (Redis) would be needed for multi-process deployments — deferred to V2.

**Why blocking calls wrapped in `asyncio.to_thread()`?** The Neo4j Python driver and Anthropic SDK are synchronous. Wrapping them in `asyncio.to_thread()` lets FastAPI serve other requests while these calls are in-flight, without rewriting the entire query layer as async.

**Why `claude-sonnet-4-6` for both steps?** Cypher generation benefits from strong reasoning; answer synthesis benefits from strong writing. Using the same model for both simplifies configuration and keeps the prompt-engineering surface consistent. Step 1 latency is ~3-8s; Step 2 streaming begins within ~2s of step 1 completing.

**Why prompt rules instead of a query validator?** A Cypher validator would need to parse the AST and enforce schema-specific constraints (correct relationship names, valid status values). The LLM is better at following natural-language rules — 14 rules cover the graph's known quirks and produce correct Cypher in 96%+ of cases. A hybrid approach (validator + prompt) is a V2 improvement.
