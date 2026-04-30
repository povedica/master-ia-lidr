"""Typed application settings from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.estimation_engine import EstimationMode

# Resolve `.env` next to the `app/` package so settings work regardless of process CWD
# (e.g. `uvicorn` launched from the monorepo root instead of `proyectos/estimador-cag/`).
_APP_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ENV_FILE = _APP_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime configuration; never hardcode secrets."""

    model_config = SettingsConfigDict(
        env_file=_DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    llm_providers: str = "openai,anthropic"
    static_fallback_enabled: bool = True
    llm_auth_fallback: bool = False
    llm_domain_guardrail_enabled: bool = True
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    app_env: str = "local"
    dev_mode: bool = False
    log_level: str = "INFO"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    anthropic_timeout_seconds: float = 30.0
    anthropic_max_tokens: int = 2048
    forced_estimation_mode: EstimationMode | None = None

    @field_validator("forced_estimation_mode", mode="before")
    @classmethod
    def _parse_forced_estimation_mode(cls, value: object) -> EstimationMode | None:
        if value is None:
            return None
        if isinstance(value, EstimationMode):
            return value
        text = str(value).strip().lower()
        if not text or text in {"none", "null", "off", "false", "0"}:
            return None
        return EstimationMode(text)


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance suitable for FastAPI Depends."""

    return Settings()
