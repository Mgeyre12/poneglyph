import time
from collections import defaultdict
from fastapi import Request, HTTPException

from api.config import get_settings


class InMemoryRateLimiter:
    """Per-IP sliding window: max_calls per window_seconds."""

    def __init__(self, max_calls: int = 30, window_seconds: int = 3600):
        self._max = max_calls
        self._window = window_seconds
        self._log: dict[str, list[float]] = defaultdict(list)

    def _ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        ip = self._ip(request)
        now = time.time()
        cutoff = now - self._window
        calls = [t for t in self._log[ip] if t > cutoff]
        calls.append(now)
        self._log[ip] = calls
        if len(calls) > self._max:
            retry_after = int(self._window - (now - calls[0]))
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "rate_limit_exceeded",
                    "message": f"Too many requests. Limit: {self._max}/hour. Try again in {retry_after}s.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

    def status(self, request: Request) -> dict:
        ip = self._ip(request)
        now = time.time()
        cutoff = now - self._window
        calls = [t for t in self._log.get(ip, []) if t > cutoff]
        return {"ip": ip, "calls_this_hour": len(calls), "limit": self._max}


# TODO (Week 10 Stage 6): bump RATE_LIMIT_PER_HOUR from 10 back to 30 once
# Turnstile is verified working on the deployed Vite frontend. See
# docs/MY_PROJECT_NOTES.md → Week 10 → Deviation 2.
rate_limiter = InMemoryRateLimiter(
    max_calls=get_settings().rate_limit_per_hour,
    window_seconds=3600,
)
