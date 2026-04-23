import time
from fastapi import APIRouter, Header, HTTPException

from api.config import get_settings
from api.core.cache import answer_cache
from api.middleware.rate_limit import rate_limiter

router = APIRouter()


def _require_admin(x_admin_token: str | None) -> None:
    settings = get_settings()
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="Admin endpoint not configured.")
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


@router.get("/admin/stats")
async def admin_stats(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)

    cache = answer_cache.stats()
    rl = rate_limiter

    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cache": cache,
        "rate_limiter": {
            "window_seconds": rl._window,
            "max_calls": rl._max,
            "tracked_ips": len(rl._log),
        },
    }
