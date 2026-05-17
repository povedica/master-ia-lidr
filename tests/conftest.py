"""Shared pytest fixtures."""

import pytest

from app.config import get_settings
from app.services.observability.bootstrap import reset_observability_for_tests
from app.services.observability.noop import NoopObservabilityAdapter


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    """Avoid stale Settings between tests that tweak environment variables."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def observability_noop_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent tests from opening real Langfuse clients via lazy ``get_observability``."""

    reset_observability_for_tests()
    noop = NoopObservabilityAdapter()
    monkeypatch.setenv("OTEL_EXPORT_ENABLED", "false")
    get_settings.cache_clear()
    init = lambda: noop  # noqa: E731
    monkeypatch.setattr("app.services.observability.bootstrap.get_observability", init)
    monkeypatch.setattr("app.services.ai_model_service.get_observability", init)
    yield
    reset_observability_for_tests()
