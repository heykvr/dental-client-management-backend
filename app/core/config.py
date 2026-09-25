from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    app_timezone: str = "Asia/Kolkata"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "dental_app"

    # Google Gemini API (free tier); used only by the backend
    gemini_api_key: str = ""
    ai_model: str = "gemini-3.5-flash-lite"
    # Max wait for an AI answer: chat is interactive, the summary runs in the background
    ai_chat_timeout_seconds: float = 15.0
    ai_summary_timeout_seconds: float = 20.0
    eval_judge_model: str = "gemini-3.6-flash"

    # Comma-separated list, e.g. "http://localhost:5173,https://app.vercel.app"
    cors_origins: str = Field(default="http://localhost:5173")
    # Sliding-window limits per client IP (see app/core/rate_limit.py)
    rate_limit_default: str = "10/minute"
    rate_limit_ai: str = "3/minute;20/day"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
