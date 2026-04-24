# Local dev

Read-me-first when you haven't touched the repo in a while. Two processes, two ports.

| Layer | Command | Port | Env file |
|---|---|---|---|
| Backend (FastAPI) | `uvicorn api.main:app --reload --port 8000` | 8000 | `.env` (repo root) |
| Frontend (Vite) | `cd web && npm run dev` | 8080 | `web/.env.local` |

The frontend reads `VITE_API_BASE_URL` from `web/.env.local` and posts to `${API_BASE_URL}/api/ask`. Match those ports or nothing works.

## Prereqs (one-time)

1. **Python 3.11+** and `pip install -r requirements.txt` from repo root.
2. **Node 20+** and `cd web && npm install`.
3. **Neo4j** — either local Neo4j Desktop running on `bolt://localhost:7687`, or Aura credentials filled in under the `NEO4J_AURA_*` vars in `.env`.
4. **Anthropic API key** in `.env` as `ANTHROPIC_API_KEY`.
5. **Copy env templates:**
   ```bash
   cp .env.example .env            # backend — fill in secrets
   cp web/.env.example web/.env.local   # frontend — defaults already point at localhost:8000
   ```

## Daily flow

**Terminal 1 — backend:**
```bash
# optional: use Aura instead of local Neo4j for the session
export NEO4J_ENV=aura      # or `local` (default)

# Turnstile off locally so you don't need real site-key round-trips
export TURNSTILE_ENABLED=false

# start with reload
uvicorn api.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/api/health`

**Terminal 2 — frontend:**
```bash
cd web
npm run dev
```

Open `http://localhost:8080`. Ask a question. The Turnstile widget will load silently (invisible mode) and issue a token; the backend ignores it when `TURNSTILE_ENABLED=false`.

## How the two connect

```
browser (localhost:8080)
  └─ POST /api/ask  →  FastAPI (localhost:8000)
                        └─ Neo4j (local or Aura)
                        └─ Anthropic API
```

Vite's dev server doesn't proxy — the frontend makes cross-origin requests directly. CORS is handled by FastAPI via `ALLOWED_ORIGINS` in `.env` (must include `http://localhost:8080`).

## Switching the frontend to hit prod

Edit `web/.env.local`:
```
VITE_API_BASE_URL=https://poneglyph-production-dfaf.up.railway.app
```
Restart `npm run dev` (Vite picks up env changes only on restart). The Turnstile widget will use the real site key and the backend will actually verify it — so don't be surprised if a dummy token gets rejected.

## Common gotchas

- **"Missing required env var VITE_API_BASE_URL"** in the browser console → `web/.env.local` is missing or the var is empty. Copy `web/.env.example`.
- **CORS error in browser console** → `ALLOWED_ORIGINS` in `.env` doesn't include `http://localhost:8080`. Fix and restart uvicorn.
- **403 `turnstile_missing`** hitting the prod backend from localhost → expected, prod requires a real Turnstile token. Either test against local backend or make sure the widget is actually issuing tokens (check network tab for a `challenges.cloudflare.com` request).
- **Neo4j `ServiceUnavailable` at :7687** → local Neo4j Desktop isn't running, or you want Aura (`NEO4J_ENV=aura`).
- **Anthropic 429** on rapid back-to-back questions → the org-level input-TPM limit. Wait 30-60s.

## Tests

```bash
# Python stress test — uses whatever NEO4J_ENV is set to
NEO4J_ENV=aura python3 tests/run_stress_test.py      # writes next numbered run file

# Frontend vitest
cd web && npm run test
```
