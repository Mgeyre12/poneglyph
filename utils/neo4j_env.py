"""
neo4j_env.py
------------
Single source of truth for Neo4j connection env vars used by non-API scripts
(query/, ingest/, pipeline/, fixes/, tests/, utils/).

The FastAPI app in api/ uses pydantic-settings directly — this helper exists
only so CLI/batch scripts can honor the same NEO4J_ENV=local|aura toggle
without pulling in pydantic.

Usage:
    from utils.neo4j_env import get_neo4j_config
    uri, user, password, database = get_neo4j_config()
    driver = GraphDatabase.driver(uri, auth=(user, password))

Env vars read:
    NEO4J_ENV                 — "local" (default) or "aura"
    NEO4J_LOCAL_URI           — required when NEO4J_ENV=local
    NEO4J_LOCAL_USER          — required when NEO4J_ENV=local
    NEO4J_LOCAL_PASSWORD      — required when NEO4J_ENV=local
    NEO4J_AURA_URI            — required when NEO4J_ENV=aura
    NEO4J_AURA_USER           — required when NEO4J_ENV=aura
    NEO4J_AURA_PASSWORD       — required when NEO4J_ENV=aura
    NEO4J_AURA_DATABASE       — optional; defaults to None (server default)
"""

import os

from dotenv import load_dotenv

load_dotenv()


def get_neo4j_config() -> tuple[str, str, str, str | None]:
    """Return (uri, user, password, database) for the current NEO4J_ENV."""
    env = os.getenv("NEO4J_ENV", "local").lower()

    if env == "aura":
        uri = os.getenv("NEO4J_AURA_URI")
        user = os.getenv("NEO4J_AURA_USER")
        password = os.getenv("NEO4J_AURA_PASSWORD")
        database = os.getenv("NEO4J_AURA_DATABASE") or None
    elif env == "local":
        uri = os.getenv("NEO4J_LOCAL_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_LOCAL_USER", "neo4j")
        password = os.getenv("NEO4J_LOCAL_PASSWORD")
        database = None
    else:
        raise ValueError(
            f"Invalid NEO4J_ENV={env!r}. Must be 'local' or 'aura'."
        )

    missing = [
        n for n, v in [("URI", uri), ("USER", user), ("PASSWORD", password)] if not v
    ]
    if missing:
        raise ValueError(
            f"NEO4J_ENV={env} but NEO4J_{env.upper()}_{missing[0]} is not set. "
            f"Check your .env file."
        )

    return uri, user, password, database
