"""Settings loading tests."""

import pytest

from app.config import Settings, get_settings


def test_settings_reads_openai_model_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test-model")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.openai_model == "gpt-test-model"


def test_get_settings_cached_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test-env")
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    assert first.app_env == "test-env"


def test_optional_anthropic_fields_have_safe_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ANTHROPIC_MAX_TOKENS", raising=False)
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key == ""
    assert settings.anthropic_model == "claude-3-5-haiku-latest"
    assert settings.anthropic_timeout_seconds == 30.0
    assert settings.anthropic_max_tokens == 2048


def test_provider_chain_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_providers == "openai,anthropic"
    assert settings.static_fallback_enabled is True
    assert settings.llm_auth_fallback is False
