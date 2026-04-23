# Deployment Guide

Stack: Next.js (Vercel) + FastAPI (Railway) + Neo4j Aura Free + Cloudflare Turnstile

---

## 1. Neo4j Aura Free

1. Go to https://console.neo4j.io → **New Instance** → **AuraDB Free**
2. Choose a region (pick closest to your Railway region)
3. Download the generated credentials file — it contains `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
4. The URI format is `neo4j+s://<id>.databases.neo4j.io` (not `bolt://`)
5. Set `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` as Railway env vars (see section 3)

Migration from local graph: see `docs/ARCHITECTURE.md` for the dump/restore steps.

---

## 2. Cloudflare Turnstile (bot protection)

Turnstile is free. No credit card required.

1. Go to https://dash.cloudflare.com → **Turnstile** (left sidebar)
2. Click **Add site**
3. Site name: `Poneglyph`
4. Domain: your Vercel domain (e.g. `poneglyph.vercel.app`) — add `localhost` as a second domain for dev
5. Widget type: **Managed** (invisible challenge, no CAPTCHA box shown to users)
6. Click **Create**
7. Copy the **Site Key** → goes in Next.js frontend as `NEXT_PUBLIC_TURNSTILE_SITE_KEY`
8. Copy the **Secret Key** → goes in Railway as `TURNSTILE_SECRET_KEY`
9. Set `TURNSTILE_ENABLED=true` in Railway env vars

Local dev: keep `TURNSTILE_ENABLED=false` in your local `.env` to bypass verification.

---

## 3. Railway (FastAPI backend)

1. Go to https://railway.app → **New Project** → **Deploy from GitHub repo**
2. Select this repo, set root directory to `/` (Railway auto-detects `api/`)
3. Set the start command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
4. Add all env vars under **Variables**:

```
NEO4J_URI=neo4j+s://<id>.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<from aura credentials file>
ANTHROPIC_API_KEY=sk-ant-...
ALLOWED_ORIGINS=https://poneglyph.vercel.app
TURNSTILE_SECRET_KEY=<from cloudflare>
TURNSTILE_ENABLED=true
ADMIN_TOKEN=<generate a random string>
```

5. Under **Settings → Networking**, enable a public domain (e.g. `poneglyph-api.up.railway.app`)
6. Verify: `curl https://poneglyph-api.up.railway.app/api/health`

---

## 4. Vercel (Next.js frontend — Week 12)

1. Import repo into Vercel, set framework to Next.js
2. Add env vars:
   - `NEXT_PUBLIC_API_URL=https://poneglyph-api.up.railway.app`
   - `NEXT_PUBLIC_TURNSTILE_SITE_KEY=<from cloudflare>`
3. Deploy

---

## 5. Anthropic spend cap (REQUIRED before public launch)

**Do this now, before enabling public access:**

1. Go to https://console.anthropic.com → **Settings → Limits**
2. Set a **monthly spend limit** (recommended: $50/month for early traffic)
3. Optionally set a daily limit too — $15/day keeps a spike from draining the monthly budget overnight
4. The API will return 529 errors if the cap is hit; the backend returns an `error` SSE event with `code: "answer_generation_failed"`

This is enforced at the Anthropic dashboard level, not in code. Do not rely on code-level guards for this.

---

## 6. Health check URLs

After deployment, verify these all return expected responses:

```bash
# Backend health
curl https://poneglyph-api.up.railway.app/api/health

# Graph counts
curl https://poneglyph-api.up.railway.app/api/stats

# Ask (streaming)
curl -N -X POST https://poneglyph-api.up.railway.app/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "who are the straw hats?"}'

# Admin stats (substitute your ADMIN_TOKEN)
curl https://poneglyph-api.up.railway.app/api/admin/stats \
  -H "X-Admin-Token: your-admin-token"
```

---

## 7. Post-launch monitoring

- **Admin endpoint**: `/api/admin/stats` — cache size, tracked IPs, rate limiter state
- **Anthropic console**: watch spend daily for the first week after launch
- **Railway logs**: all requests emit structured JSON log lines; filter by `"path":"/api/ask"` for query volume
