"""
ask_service.py
--------------
Wraps query/ask.py as an async event-emitting service for the FastAPI layer.
The terminal CLI in query/ask.py is untouched — this is an adapter.

Events emitted (via async generator):
  step_start     {"step": str, "label": str, "ts": str}
  step_complete  {"step": str, "duration_ms": int, "output": dict}
  answer_chunk   {"text": str}
  done           {"citations": list, "meta": dict}
  error          {"code": str, "message": str}
"""

import sys
import time
import json
import asyncio
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

# Import from query/ask.py without running its CLI
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "query"))
import ask as _ask

import anthropic
from neo4j import GraphDatabase

from api.config import get_settings
from api.core.cache import answer_cache

settings = get_settings()


def _run_cypher(cypher: str) -> list[dict]:
    """Run Cypher using the api's Aura-aware settings (not query/ask.py's CLI env vars)."""
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            result = session.run(cypher, timeout=5)
            return [dict(r) for r in result]
    finally:
        driver.close()

_client: anthropic.Anthropic | None = None
_schema: str | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _get_schema() -> str:
    global _schema
    if _schema is None:
        _schema = _ask.load_schema()
    return _schema


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _question_hash(question: str) -> str:
    return hashlib.sha256(question.strip().lower().encode()).hexdigest()[:12]


_CITATION_TOKEN_RE = re.compile(r"\[\[Ch\.(\d+)\|([^\]]+)\]\]")


def _extract_citations(answer_text: str) -> list[dict]:
    """Return the citations the LLM actually emitted in its answer.

    Scans the rendered answer for `[[Ch.NNN|Arc Name]]` tokens (the same regex
    the frontend uses) and returns a deduped list shaped to match the
    frontend's RobinAnswer.citations type: `[{chapter: int, title: str}]`.
    Order preserved; first occurrence wins on duplicates.
    """
    citations: list[dict] = []
    seen: set[int] = set()
    for match in _CITATION_TOKEN_RE.finditer(answer_text):
        chapter = int(match.group(1))
        if chapter in seen:
            continue
        seen.add(chapter)
        citations.append({"chapter": chapter, "title": match.group(2).strip()})
    return citations


async def run_ask(
    question: str,
    session_id: str | None = None,
    history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted strings.
    Each yield is a complete SSE event (event: ...\ndata: ...\n\n).
    """
    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    t_total = time.time()
    has_history = bool(history)

    # ── Cache check ───────────────────────────────────────────────────────────
    # Cache is keyed on question only; same Q with different conversational
    # context can yield different answers, so any history bypasses the cache.
    cached = None if has_history else answer_cache.get(question)
    if cached:
        yield sse("step_start", {"step": "cache_hit", "label": "Serving cached answer", "ts": _now()})
        for chunk in _chunk_text(cached):
            yield sse("answer_chunk", {"text": chunk})
        yield sse("done", {
            "citations": [],
            "meta": {
                "total_duration_ms": round((time.time() - t_total) * 1000),
                "model": _ask.MODEL,
                "cached": True,
                "session_id": session_id,
            },
        })
        return

    client = _get_client()
    schema = _get_schema()

    # ── Step 1: generate Cypher ───────────────────────────────────────────────
    yield sse("step_start", {"step": "generate_cypher", "label": "Generating graph query", "ts": _now()})
    t0 = time.time()
    try:
        cypher = await asyncio.to_thread(
            _ask.question_to_cypher, client, question, schema, history
        )
    except Exception as e:
        yield sse("error", {"code": "cypher_generation_failed", "message": str(e)})
        return
    cypher_ms = round((time.time() - t0) * 1000)

    valid, reason = _ask.validate_cypher(cypher)
    if not valid:
        yield sse("step_complete", {
            "step": "generate_cypher",
            "duration_ms": cypher_ms,
            "output": {"cypher": cypher, "valid": False},
        })
        yield sse("error", {"code": "cypher_validation_failed", "message": reason})
        return

    yield sse("step_complete", {
        "step": "generate_cypher",
        "duration_ms": cypher_ms,
        "output": {"cypher": cypher, "valid": True},
    })

    # ── Step 2: run query ─────────────────────────────────────────────────────
    yield sse("step_start", {"step": "run_query", "label": "Running query against knowledge graph", "ts": _now()})
    t0 = time.time()
    try:
        results = await asyncio.to_thread(_run_cypher, cypher)
    except Exception as e:
        yield sse("error", {"code": "query_failed", "message": str(e)})
        return
    query_ms = round((time.time() - t0) * 1000)

    yield sse("step_complete", {
        "step": "run_query",
        "duration_ms": query_ms,
        "output": {"rows_returned": len(results)},
    })

    # ── Step 2b: resolve chapter→arc so the answer LLM can emit inline citations
    arc_map = await asyncio.to_thread(_ask.build_arc_map, results, _run_cypher)

    # ── Step 3: stream answer ─────────────────────────────────────────────────
    yield sse("step_start", {"step": "write_answer", "label": "Writing answer", "ts": _now()})

    answer_parts: list[str] = []
    try:
        system = _ask.ANSWER_SYSTEM_PROMPT
        user_prompt = _ask._build_answer_user_prompt(
            question, cypher, results, arc_map, history
        )
        stream = await asyncio.to_thread(
            lambda: client.messages.stream(
                model=_ask.MODEL,
                max_tokens=_ask.MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
            )
        )
        with stream as s:
            for text in s.text_stream:
                answer_parts.append(text)
                yield sse("answer_chunk", {"text": text})
    except Exception as e:
        yield sse("error", {"code": "answer_generation_failed", "message": str(e)})
        return

    full_answer = "".join(answer_parts)
    if not has_history:
        answer_cache.set(question, full_answer)

    citations = _extract_citations(full_answer)
    total_ms = round((time.time() - t_total) * 1000)

    yield sse("done", {
        "citations": citations,
        "meta": {
            "total_duration_ms": total_ms,
            "model": _ask.MODEL,
            "cached": False,
            "question_hash": _question_hash(question),
            "session_id": session_id,
        },
    })


def _chunk_text(text: str, size: int = 20) -> list[str]:
    """Split cached answer into word-boundary chunks for streaming."""
    words = text.split(" ")
    chunks, buf = [], []
    for w in words:
        buf.append(w)
        if len(buf) >= size:
            chunks.append(" ".join(buf) + " ")
            buf = []
    if buf:
        chunks.append(" ".join(buf))
    return chunks
