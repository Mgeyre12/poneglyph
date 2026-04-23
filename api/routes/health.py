from fastapi import APIRouter
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

from api.config import get_settings
from api.core.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()

    neo4j_status = "connected"
    try:
        driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
        with driver.session() as s:
            s.run("RETURN 1")
        driver.close()
    except Exception:
        neo4j_status = "error"

    anthropic_status = "configured" if settings.anthropic_api_key else "missing"

    return HealthResponse(
        status="ok",
        neo4j=neo4j_status,
        anthropic=anthropic_status,
        version=settings.version,
    )
