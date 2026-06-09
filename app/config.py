"""Typed application settings from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    llm_call_persist_enabled: bool = False
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
    estimation_output_tokens_max: int = Field(default=2048, ge=1)
    structured_output_max_attempts: int = Field(default=3, ge=1, le=10)
    max_attachment_size_bytes: int = Field(
        default=10_485_760,
        ge=1,
        description="Maximum decoded bytes per attachment file (default 10 MB).",
    )
    max_attachment_context_chars: int = Field(
        default=131_072,
        ge=1,
        description="Maximum characters of extracted attachment text injected into prompts.",
    )
    allowed_attachment_mime_types: str = Field(
        default=(
            "text/plain,text/markdown,application/pdf,"
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        description="Comma-separated MIME types allowed for session attachment extraction.",
    )
    prompt_estimation_version: str = Field(
        default="",
        description=(
            "Optional prompt bundle under app/prompts/estimation/ (e.g. v1). "
            "Empty uses v2 (default)."
        ),
    )
    guardrail_rules_version: str = Field(
        default="",
        max_length=64,
        description="Optional override for guardrail rules version metadata (empty uses registry default).",
    )
    estimation_min_output_confidence: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Minimum structured-result confidence before output semantic downgrade.",
    )
    guardrail_rollout_pii_basic: str = Field(
        default="",
        max_length=16,
        description="When set to disabled|log_only|enforce overrides registry rollout for pii_basic.",
    )
    guardrail_rollout_prompt_injection_patterns: str = Field(
        default="",
        max_length=16,
        description="Overrides registry rollout for prompt_injection_patterns when non-empty.",
    )
    guardrail_rollout_estimation_domain_relevance: str = Field(
        default="",
        max_length=16,
        description="Overrides registry rollout for estimation_domain_relevance when non-empty.",
    )
    guardrail_rollout_moderation_toxicity: str = Field(
        default="",
        max_length=16,
        description="Overrides registry rollout for moderation_toxicity when non-empty.",
    )
    guardrail_rollout_output_confidence_floor: str = Field(
        default="",
        max_length=16,
        description="Overrides registry rollout for output_confidence_floor when non-empty.",
    )
    guardrail_rollout_output_sensitive_leakage: str = Field(
        default="",
        max_length=16,
        description="Overrides registry rollout for output_sensitive_leakage when non-empty.",
    )
    guardrail_rollout_output_useless_placeholder: str = Field(
        default="",
        max_length=16,
        description="Overrides registry rollout for output_useless_placeholder when non-empty.",
    )
    # --- Semantic cache (feature 013): guarded inference reuse ---
    semantic_cache_enabled: bool = Field(
        default=False,
        description="When true, allow serving validated semantic cache hits (not log-only).",
    )
    semantic_cache_log_only: bool = Field(
        default=True,
        description="When true, run lookup diagnostics but never bypass the LLM.",
    )
    semantic_cache_redis_url: str = Field(
        default="",
        description="Redis DSN for vector cache; empty disables remote store unless memory store is on.",
    )
    semantic_cache_namespace: str = Field(
        default="semantic:estimation",
        max_length=128,
        description="Key/index namespace prefix for semantic cache entries.",
    )
    semantic_cache_ttl_seconds: int = Field(
        default=86_400,
        ge=60,
        le=86_400 * 120,
        description="TTL for validated semantic cache entries.",
    )
    semantic_cache_similarity_threshold: float = Field(
        default=0.92,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity to serve a cache hit when enabled.",
    )
    semantic_cache_max_candidates: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Max neighbors retrieved within a bucket for diagnostics.",
    )
    semantic_cache_embedding_provider: str = Field(
        default="openai",
        max_length=32,
        description="Embedding provider label (implementation may still be fake in tests).",
    )
    semantic_cache_embedding_model: str = Field(
        default="text-embedding-3-small",
        max_length=128,
        description="Embedding model id for metadata and future OpenAI calls.",
    )
    semantic_cache_embedding_model_version: str = Field(
        default="text-embedding-3-small:default",
        max_length=128,
        description="Version label included in the deterministic bucket.",
    )
    semantic_cache_embedding_timeout_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=120.0,
        description="Timeout for embedding provider calls when implemented.",
    )
    semantic_cache_max_payload_bytes: int = Field(
        default=262_144,
        ge=4096,
        le=8_388_608,
        description="Maximum serialized cache entry size.",
    )
    semantic_cache_enabled_endpoints: str = Field(
        default="api_v2_estimate",
        max_length=512,
        description="Comma-separated endpoint allowlist (e.g. api_v2_estimate).",
    )
    semantic_cache_enabled_tenants: str = Field(
        default="",
        max_length=1024,
        description="Optional comma-separated tenant allowlist; empty means no tenant filter.",
    )
    semantic_cache_enabled_operations: str = Field(
        default="estimation_v2",
        max_length=512,
        description="Comma-separated operation allowlist.",
    )
    semantic_cache_cache_schema_version: str = Field(
        default="1",
        max_length=16,
        description="Semantic cache artifact schema version (bucket component).",
    )
    semantic_cache_use_memory_store: bool = Field(
        default=False,
        description="When true and redis URL empty, use in-process store (single worker only).",
    )
    # --- Observability (feature 014): Langfuse / OTEL export ---
    otel_export_enabled: bool = Field(
        default=False,
        description="When true, export OTEL/Langfuse traces (requires Langfuse API keys).",
    )
    langfuse_public_key: str = Field(
        default="",
        description="Langfuse project public key (never commit real values).",
    )
    langfuse_secret_key: str = Field(
        default="",
        description="Langfuse project secret key (never commit real values).",
    )
    langfuse_base_url: str = Field(
        default="https://cloud.langfuse.com",
        description="Langfuse API base URL (EU cloud default).",
    )
    otel_service_name: str = Field(
        default="estimator-local",
        max_length=128,
        description="OpenTelemetry service.name resource attribute.",
    )
    app_version: str = Field(
        default="0.0.0-local",
        max_length=128,
        description="Application build/version label for observability metadata.",
    )
    app_release: str = Field(
        default="local",
        max_length=128,
        description="Deployed release identifier for observability metadata.",
    )
    langfuse_debug: bool = Field(
        default=False,
        description="Enable Langfuse SDK debug logging (never in production by default).",
    )
    langfuse_sample_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="App-side trace sampling rate when export is enabled (0.0–1.0).",
    )
    langfuse_capture_inputs: bool = Field(
        default=False,
        description="Capture sanitized LLM inputs in Langfuse generations.",
    )
    langfuse_capture_outputs: bool = Field(
        default=False,
        description="Capture sanitized LLM outputs in Langfuse generations.",
    )
    langfuse_capture_usage: bool = Field(
        default=True,
        description="Send token usage_details when the provider returns usage.",
    )
    langfuse_capture_cost: bool = Field(
        default=True,
        description="Send explicit cost_details when cost is trustworthy.",
    )
    # --- Session integration tests (feature-022) ---
    session_integration_test_llm_model: str = Field(
        default="",
        max_length=128,
        description=(
            "Optional OpenAI model id for pytest session integration harness "
            "(empty uses OPENAI_MODEL)."
        ),
    )
    session_integration_test_use_real_llm: bool = Field(
        default=False,
        description=(
            "When true, session integration tests call the real structured LLM "
            "instead of FakeStructuredLLM (requires OPENAI_API_KEY)."
        ),
    )
    # --- Actor-Critic-Boss orchestration (feature 026) ---
    acb_enabled: bool = Field(
        default=False,
        description="Global kill switch for ACB orchestration on allowed endpoints.",
    )
    acb_enabled_endpoints: str = Field(
        default="session_estimate",
        max_length=512,
        description="Comma-separated endpoint allowlist for ACB activation.",
    )
    acb_max_iterations: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Maximum Actor passes per ACB run (inclusive of initial pass).",
    )
    acb_allow_synthesize: bool = Field(
        default=True,
        description="When true, Boss may synthesize a final estimate on budget exhaustion.",
    )
    acb_blocking_severities: str = Field(
        default="critical,major",
        max_length=64,
        description="Comma-separated Critic severities treated as blocking for revision.",
    )
    acb_force_enabled_in_dev: bool = Field(
        default=False,
        description="When APP_ENV=local and DEV_MODE=true, force ACB on allowed endpoints.",
    )
    acb_critic_model: str = Field(
        default="",
        max_length=128,
        description="Optional LiteLLM model override for Critic role (empty uses OPENAI_MODEL).",
    )
    acb_boss_model: str = Field(
        default="",
        max_length=128,
        description="Optional LiteLLM model override for Boss role (empty uses OPENAI_MODEL).",
    )
    acb_prompt_version: str = Field(
        default="v1",
        max_length=16,
        description="ACB prompt bundle version subdirectory under app/prompts/acb/.",
    )
    # --- Embedding pipeline (feature-032): OpenAI embedder for ingest ---
    embedding_pipeline_model: str = Field(
        default="text-embedding-3-small",
        max_length=128,
        description="OpenAI embedding model for the embedding pipeline ingest path.",
    )
    embedding_pipeline_batch_size: int = Field(
        default=100,
        ge=1,
        le=2048,
        description="Batch size for embed_many API calls (one request per batch).",
    )
    # --- Semantic search persistence (feature-036): Postgres + pgvector ---
    database_url: str = Field(
        default="",
        description=(
            "Async SQLAlchemy DSN for Postgres (postgresql+asyncpg://...). "
            "Empty disables DB-backed features until configured."
        ),
    )

    def acb_blocking_severities_set(self) -> frozenset[str]:
        return frozenset(
            part.strip()
            for part in self.acb_blocking_severities.split(",")
            if part.strip()
        )

    def acb_active_for_endpoint(self, endpoint: str) -> bool:
        allowed = {p.strip() for p in self.acb_enabled_endpoints.split(",") if p.strip()}
        if not allowed:
            return False
        return endpoint.strip() in allowed

    def acb_requested(
        self,
        orchestration_override: str | None,
        *,
        endpoint: str,
    ) -> bool:
        override = (orchestration_override or "").strip().lower()
        if override == "single_pass":
            return False
        if override == "acb":
            return True
        if override == "default" or not override:
            if self.dev_mode and self.app_env == "local" and self.acb_force_enabled_in_dev:
                return self.acb_active_for_endpoint(endpoint)
            return self.acb_enabled and self.acb_active_for_endpoint(endpoint)
        return self.acb_enabled and self.acb_active_for_endpoint(endpoint)

    def resolved_session_integration_test_openai_model(self) -> str:
        """Model id used by the session integration pytest harness."""

        override = self.session_integration_test_llm_model.strip()
        return override if override else self.openai_model

    @model_validator(mode="after")
    def _validate_langfuse_keys_when_export_enabled(self) -> Self:
        if not self.otel_export_enabled:
            return self
        if not self.langfuse_public_key.strip():
            raise ValueError("LANGFUSE_PUBLIC_KEY is required when OTEL_EXPORT_ENABLED=true")
        if not self.langfuse_secret_key.strip():
            raise ValueError("LANGFUSE_SECRET_KEY is required when OTEL_EXPORT_ENABLED=true")
        if not self.langfuse_base_url.strip():
            raise ValueError("LANGFUSE_BASE_URL is required when OTEL_EXPORT_ENABLED=true")
        return self

    def observability_export_active(self) -> bool:
        """True when export is enabled and Langfuse credentials are configured."""

        if not self.otel_export_enabled:
            return False
        return bool(
            self.langfuse_public_key.strip()
            and self.langfuse_secret_key.strip()
            and self.langfuse_base_url.strip()
        )

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

    def allowed_attachment_mime_types_list(self) -> list[str]:
        """Parsed MIME allowlist for attachment extraction (lowercase, trimmed)."""

        return [
            part.strip().lower()
            for part in self.allowed_attachment_mime_types.split(",")
            if part.strip()
        ]

    def semantic_cache_feature_active(self) -> bool:
        """True when semantic cache diagnostics or serving may run."""

        return self.semantic_cache_enabled or self.semantic_cache_log_only

    def semantic_cache_fully_off(self) -> bool:
        """True when the app must skip embeddings, vector lookup, and remote cache I/O."""

        return not self.semantic_cache_enabled and not self.semantic_cache_log_only

    def semantic_cache_store_available(self) -> bool:
        """True when a backing store is configured (Redis URL or explicit memory store)."""

        return bool(self.semantic_cache_redis_url.strip()) or self.semantic_cache_use_memory_store

    def semantic_cache_allowed_endpoint(self, endpoint: str) -> bool:
        allowed = {p.strip() for p in self.semantic_cache_enabled_endpoints.split(",") if p.strip()}
        return endpoint.strip() in allowed if allowed else False

    def semantic_cache_allowed_operation(self, operation: str) -> bool:
        allowed = {p.strip() for p in self.semantic_cache_enabled_operations.split(",") if p.strip()}
        return operation.strip() in allowed if allowed else False

    def semantic_cache_allowed_tenant(self, tenant_id: str) -> bool:
        raw = self.semantic_cache_enabled_tenants.strip()
        if not raw:
            return True
        allowed = {p.strip() for p in raw.split(",") if p.strip()}
        return tenant_id.strip() in allowed


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance suitable for FastAPI Depends."""

    return Settings()
