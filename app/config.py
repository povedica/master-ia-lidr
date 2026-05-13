"""Typed application settings from environment variables."""

from functools import lru_cache
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.estimation_engine import EstimationMode

# Resolve `.env` next to the `app/` package so settings work regardless of process CWD
# (e.g. `uvicorn` launched from any working directory).
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
    estimation_output_persist_enabled: bool = False
    estimation_stats_log_enabled: bool = False
    estimation_stats_log_path: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    app_env: str = "local"
    dev_mode: bool = False
    log_level: str = "INFO"
    frontend_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated browser origins allowed for CORS (local Vite defaults).",
    )
    anthropic_api_key: str = ""
    # Claude 3.5 Haiku snapshots were retired (see SDK ``DEPRECATED_MODELS``); use current Haiku 4.5 id.
    anthropic_model: str = "claude-haiku-4-5-20251001"
    anthropic_timeout_seconds: float = 30.0
    # LiteLLM: documented default routing label (structured logs only); not a credential.
    default_llm_provider: str = "unset"
    # Canonical LiteLLM-style id for documentation defaults; runtime model ids come from OPENAI_MODEL / ANTHROPIC_MODEL.
    default_llm_model: str = "openai/gpt-4o-mini"
    gemini_api_key: str = ""
    forced_estimation_mode: EstimationMode | None = None
    structured_output_max_attempts: int = Field(default=3, ge=1, le=10)
    prompt_estimation_version: str = Field(
        default="",
        description="Optional prompt bundle version directory under app/prompts/estimation/ (e.g. v1).",
    )
    # Per-mode max completion tokens passed to OpenAI and Anthropic for that estimation mode.
    estimation_basic_output_tokens_max: int = Field(default=1024, ge=1)
    estimation_standard_output_tokens_max: int = Field(default=2048, ge=1)
    estimation_professional_output_tokens_max: int = Field(default=4096, ge=1)
    estimation_expert_review_output_tokens_max: int = Field(default=8192, ge=1)

    def openai_litellm_model_id(self) -> str:
        """Return a LiteLLM chat model id for the OpenAI chain entry."""

        raw = self.openai_model.strip()
        if "/" in raw:
            return raw
        return f"openai/{raw}"

    def anthropic_litellm_model_id(self) -> str:
        """Return a LiteLLM chat model id for the Anthropic chain entry."""

        raw = self.anthropic_model.strip()
        if "/" in raw:
            return raw
        return f"anthropic/{raw}"

    def frontend_origins_list(self) -> list[str]:
        """Return trimmed non-empty origins from ``frontend_origins``."""

        parts = [part.strip() for part in self.frontend_origins.split(",")]
        return [part for part in parts if part]

    def completion_token_cap_for_mode(self, mode: EstimationMode) -> int:
        """Upper bound passed to providers as max output tokens for this mode."""

        mapping: dict[EstimationMode, int] = {
            EstimationMode.BASIC: self.estimation_basic_output_tokens_max,
            EstimationMode.STANDARD: self.estimation_standard_output_tokens_max,
            EstimationMode.PROFESSIONAL: self.estimation_professional_output_tokens_max,
            EstimationMode.EXPERT_REVIEW: self.estimation_expert_review_output_tokens_max,
        }
        return mapping[mode]

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
