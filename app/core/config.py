from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "dental_app"

    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-4-5-20251001"
    ai_timeout_seconds: float = 30.0

    # Comma-separated list, e.g. "http://localhost:5173,https://app.vercel.app"
    cors_origins: str = Field(default="http://localhost:5173")
    rate_limit_register: str = "5/minute;30/day"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
