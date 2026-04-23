import time
from fastapi import APIRouter
from neo4j import GraphDatabase

from api.config import get_settings
from api.core.schemas import StatsResponse

router = APIRouter()

_stats_cache: dict = {}
_stats_ts: float = 0.0
_STATS_TTL = 3600


@router.get("/stats", response_model=StatsResponse)
async def stats():
    global _stats_cache, _stats_ts

    if _stats_cache and (time.time() - _stats_ts) < _STATS_TTL:
        return StatsResponse(**_stats_cache)

    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as s:
            counts = {}
            for label in ("Character", "Chapter", "Arc", "Organization", "DevilFruit", "Location", "Occupation"):
                result = s.run(f"MATCH (n:{label}) RETURN count(n) AS n").single()
                counts[label] = result["n"] if result else 0
    finally:
        driver.close()

    _stats_cache = {
        "characters": counts["Character"],
        "chapters": counts["Chapter"],
        "arcs": counts["Arc"],
        "organizations": counts["Organization"],
        "devil_fruits": counts["DevilFruit"],
        "locations": counts["Location"],
        "occupations": counts["Occupation"],
    }
    _stats_ts = time.time()
    return StatsResponse(**_stats_cache)
