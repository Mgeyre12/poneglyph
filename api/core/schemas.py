from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    session_id: str | None = None
    turnstile_token: str | None = None


class HealthResponse(BaseModel):
    status: str
    neo4j: str
    anthropic: str
    version: str


class StatsResponse(BaseModel):
    characters: int
    chapters: int
    arcs: int
    organizations: int
    devil_fruits: int
    locations: int
    occupations: int
