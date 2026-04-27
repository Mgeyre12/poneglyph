from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Conversation history is sent stateless from the client every request. We cap
# at 6 messages (3 user + 3 assistant pairs). Going deeper bloats prompts and
# rarely helps reference resolution; if more is sent we keep only the tail.
MAX_HISTORY_MESSAGES = 6


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    session_id: str | None = None
    turnstile_token: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)

    @field_validator("history")
    @classmethod
    def _truncate_history(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if len(v) > MAX_HISTORY_MESSAGES:
            return v[-MAX_HISTORY_MESSAGES:]
        return v


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
