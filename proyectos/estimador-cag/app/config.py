"""Typed application settings from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration; never hardcode secrets."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    app_env: str = "local"
    dev_mode: bool = False
    log_level: str = "INFO"
    anthropic_api_key: str = ""
    anthropic_model: str = ""


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance suitable for FastAPI Depends."""

    return Settings()
