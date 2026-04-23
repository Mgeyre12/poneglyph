import httpx
from fastapi import HTTPException

from api.config import get_settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str | None) -> None:
    """
    Verify a Cloudflare Turnstile token.
    Raises 403 if verification fails.
    Skips verification if TURNSTILE_ENABLED=false (dev mode).
    """
    settings = get_settings()
    if not settings.turnstile_enabled:
        return

    if not token:
        raise HTTPException(
            status_code=403,
            detail={"code": "turnstile_missing", "message": "Bot verification token required."},
        )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            VERIFY_URL,
            data={
                "secret": settings.turnstile_secret_key,
                "response": token,
            },
            timeout=5.0,
        )

    data = resp.json()
    if not data.get("success"):
        codes = data.get("error-codes", [])
        raise HTTPException(
            status_code=403,
            detail={"code": "turnstile_failed", "message": f"Bot verification failed: {codes}"},
        )
