"""Settings resolution for session integration tests."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings
from tests.support.integration_settings import (
    SessionIntegrationTestConfigError,
    integration_test_settings,
    session_integration_uses_real_llm,
)


def test_resolved_session_integration_test_openai_model_prefers_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("SESSION_INTEGRATION_TEST_LLM_MODEL", "gpt-4o")
    get_settings.cache_clear()
    assert Settings().resolved_session_integration_test_openai_model() == "gpt-4o"
    get_settings.cache_clear()


def test_integration_test_settings_applies_model_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_INTEGRATION_TEST_LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("SESSION_INTEGRATION_TEST_USE_REAL_LLM", "false")
    get_settings.cache_clear()
    settings = integration_test_settings()
    assert settings.openai_model == "gpt-4.1-mini"
    assert settings.openai_api_key == "test-key"
    get_settings.cache_clear()


def test_integration_test_settings_real_llm_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_INTEGRATION_TEST_USE_REAL_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(SessionIntegrationTestConfigError):
        integration_test_settings()
    get_settings.cache_clear()


def test_session_integration_uses_real_llm_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_INTEGRATION_TEST_USE_REAL_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    assert session_integration_uses_real_llm() is True
    get_settings.cache_clear()
