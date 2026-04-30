"""Settings loading tests."""

import pytest
from pydantic import ValidationError

import app.config as app_config
from app.config import Settings, get_settings
from app.services.estimation_engine import EstimationMode


def test_default_env_file_is_beside_app_package() -> None:
    """`.env` is anchored to the service root, not the process CWD."""
    root = app_config._APP_ROOT
    assert (root / "app" / "main.py").is_file()
    assert app_config._DEFAULT_ENV_FILE == root / ".env"


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
    assert settings.llm_domain_guardrail_enabled is True
    assert settings.estimation_output_persist_enabled is False


def test_domain_guardrail_can_be_disabled_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DOMAIN_GUARDRAIL_ENABLED", "false")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.llm_domain_guardrail_enabled is False


def test_estimation_output_persist_can_be_enabled_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESTIMATION_OUTPUT_PERSIST_ENABLED", "true")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.estimation_output_persist_enabled is True


def test_forced_estimation_mode_parses_enum_value() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="sk-test",
        forced_estimation_mode="expert_review",
    )
    assert settings.forced_estimation_mode == EstimationMode.EXPERT_REVIEW


def test_forced_estimation_mode_none_when_blank() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="sk-test",
        forced_estimation_mode="",
    )
    assert settings.forced_estimation_mode is None


def test_forced_estimation_mode_none_when_off_sentinel() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="sk-test",
        forced_estimation_mode="off",
    )
    assert settings.forced_estimation_mode is None


def test_forced_estimation_mode_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            openai_api_key="sk-test",
            forced_estimation_mode="not-a-mode",
        )
