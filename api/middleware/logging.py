import json
import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("poneglyph.access")


def _ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Emits one JSON log line per request:
      {ts, method, path, status, latency_ms, ip}

    The ask route logs its own richer line
    ({question_hash, cypher_hash, rows, cached}) — this middleware handles
    everything else and provides the base timing for all routes.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.time()
        response = await call_next(request)
        latency_ms = round((time.time() - t0) * 1000)

        logger.info(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": latency_ms,
            "ip": _ip(request),
        }))
        return response
