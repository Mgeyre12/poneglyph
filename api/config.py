from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # FastAPI / security
    allowed_origins: str = "http://localhost:3000"
    turnstile_secret_key: str = ""
    turnstile_enabled: bool = False
    admin_token: str = ""

    # App
    version: str = "0.1.0"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
