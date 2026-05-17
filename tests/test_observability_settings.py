"""Observability / Langfuse settings (feature-014)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

_OBSERVABILITY_ENV_VARS = [
    "OTEL_EXPORT_ENABLED",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_BASE_URL",
    "OTEL_SERVICE_NAME",
    "APP_VERSION",
    "APP_RELEASE",
    "LANGFUSE_DEBUG",
    "LANGFUSE_SAMPLE_RATE",
    "LANGFUSE_CAPTURE_INPUTS",
    "LANGFUSE_CAPTURE_OUTPUTS",
    "LANGFUSE_CAPTURE_USAGE",
    "LANGFUSE_CAPTURE_COST",
]


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_observability_defaults_match_feature_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_var in _OBSERVABILITY_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)
    s = _settings()
    assert s.otel_export_enabled is False
    assert s.langfuse_public_key == ""
    assert s.langfuse_secret_key == ""
    assert s.langfuse_base_url == "https://cloud.langfuse.com"
    assert s.otel_service_name == "estimator-local"
    assert s.app_version == "0.0.0-local"
    assert s.app_release == "local"
    assert s.langfuse_debug is False
    assert s.langfuse_sample_rate == 0.0
    assert s.langfuse_capture_inputs is False
    assert s.langfuse_capture_outputs is False
    assert s.langfuse_capture_usage is True
    assert s.langfuse_capture_cost is True
    assert s.observability_export_active() is False


def test_export_enabled_requires_langfuse_keys() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _settings(
            otel_export_enabled=True,
            langfuse_public_key="",
            langfuse_secret_key="",
        )
    assert "LANGFUSE_PUBLIC_KEY" in str(exc_info.value)


def test_export_enabled_accepts_valid_keys() -> None:
    s = _settings(
        otel_export_enabled=True,
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
    )
    assert s.observability_export_active() is True


def test_langfuse_sample_rate_rejects_above_one() -> None:
    with pytest.raises(ValidationError):
        _settings(langfuse_sample_rate=1.5)


def test_langfuse_sample_rate_rejects_below_zero() -> None:
    with pytest.raises(ValidationError):
        _settings(langfuse_sample_rate=-0.01)
