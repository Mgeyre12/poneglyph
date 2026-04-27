import hashlib
import json
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.core.ask_service import run_ask
from api.core.schemas import AskRequest
from api.middleware.rate_limit import rate_limiter
from api.middleware.turnstile import verify_turnstile

router = APIRouter()
logger = logging.getLogger("poneglyph.ask")


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]


@router.post("/ask")
async def ask(body: AskRequest, request: Request):
    # Rate limit check (raises 429 if exceeded)
    rate_limiter.check(request)

    # Turnstile verification (raises 403 if failed)
    await verify_turnstile(body.turnstile_token)

    t_start = time.time()

    async def event_stream():
        cypher_captured = None
        rows_captured = 0

        history_payload = [m.model_dump() for m in body.history]
        async for chunk in run_ask(body.question, body.session_id, history_payload):
            # Capture cypher + row count for structured logging
            if '"step": "run_query"' in chunk and '"rows_returned"' in chunk:
                try:
                    data = json.loads(chunk.split("data: ", 1)[1])
                    rows_captured = data.get("output", {}).get("rows_returned", 0)
                except Exception:
                    pass
            if '"step": "generate_cypher"' in chunk and '"cypher"' in chunk:
                try:
                    data = json.loads(chunk.split("data: ", 1)[1])
                    cypher_captured = data.get("output", {}).get("cypher")
                except Exception:
                    pass
            yield chunk

        latency_ms = round((time.time() - t_start) * 1000)
        logger.info(json.dumps({
            "ip": request.client.host if request.client else "unknown",
            "question_hash": _hash(body.question),
            "cypher_hash": _hash(cypher_captured) if cypher_captured else None,
            "rows": rows_captured,
            "latency_ms": latency_ms,
            "session_id": body.session_id,
        }))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
