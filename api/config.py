from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Which Neo4j backend to use: "local" or "aura"
    neo4j_env: str = "local"

    # Local Neo4j (dev)
    neo4j_local_uri: str = "bolt://localhost:7687"
    neo4j_local_user: str = "neo4j"
    neo4j_local_password: str = ""

    # Neo4j Aura (production)
    neo4j_aura_uri: str = ""
    neo4j_aura_user: str = ""
    neo4j_aura_password: str = ""
    neo4j_aura_database: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # FastAPI / security
    allowed_origins: str = "http://localhost:3000"
    turnstile_secret_key: str = ""
    turnstile_enabled: bool = False
    admin_token: str = ""
    rate_limit_per_hour: int = 30

    # App
    version: str = "0.1.0"

    @property
    def neo4j_uri(self) -> str:
        return self.neo4j_aura_uri if self.neo4j_env == "aura" else self.neo4j_local_uri

    @property
    def neo4j_user(self) -> str:
        return self.neo4j_aura_user if self.neo4j_env == "aura" else self.neo4j_local_user

    @property
    def neo4j_password(self) -> str:
        return self.neo4j_aura_password if self.neo4j_env == "aura" else self.neo4j_local_password

    @property
    def neo4j_database(self) -> str | None:
        if self.neo4j_env == "aura" and self.neo4j_aura_database:
            return self.neo4j_aura_database
        return None

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
