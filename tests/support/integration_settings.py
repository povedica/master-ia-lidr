"""Settings helpers for session integration pytest runs."""

from __future__ import annotations

from app.config import Settings


class SessionIntegrationTestConfigError(ValueError):
    """Invalid combination of session integration test environment variables."""


def session_integration_uses_real_llm() -> bool:
    return Settings().session_integration_test_use_real_llm


def integration_test_settings() -> Settings:
    """Build Settings for ``tests/test_sessions_integration.py`` from environment."""

    loaded = Settings()
    model = loaded.resolved_session_integration_test_openai_model()
    updates: dict[str, object] = {
        "openai_model": model,
        "llm_domain_guardrail_enabled": False,
        "semantic_cache_enabled": False,
        "max_attachment_context_chars": 8_000,
    }
    if loaded.session_integration_test_use_real_llm:
        if not loaded.openai_api_key.strip():
            raise SessionIntegrationTestConfigError(
                "OPENAI_API_KEY is required when SESSION_INTEGRATION_TEST_USE_REAL_LLM=true"
            )
    else:
        updates["openai_api_key"] = "test-key"
    return loaded.model_copy(update=updates)
