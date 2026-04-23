"""
main.py — Poneglyph FastAPI backend

Endpoints:
  GET  /api/health        — Neo4j + Anthropic connectivity check
  GET  /api/stats         — Graph node counts (1h cache)
  POST /api/ask           — Streaming SSE question answering
  GET  /api/admin/stats   — Admin monitoring (requires X-Admin-Token header)

Run locally:
  uvicorn api.main:app --reload --port 8000
"""

import logging
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.middleware.logging import StructuredLoggingMiddleware
from api.routes import ask, health, stats, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger("poneglyph")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(json.dumps({
        "event": "startup",
        "version": settings.version,
        "neo4j_uri": settings.neo4j_uri,
        "turnstile_enabled": settings.turnstile_enabled,
        "allowed_origins": settings.origins_list,
    }))
    yield
    logger.info(json.dumps({"event": "shutdown"}))


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Poneglyph API",
        version=settings.version,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(StructuredLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    app.include_router(ask.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(json.dumps({"event": "unhandled_error", "error": str(exc)}))
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": "Something went wrong."},
        )

    return app


app = create_app()
