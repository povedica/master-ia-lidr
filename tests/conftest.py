"""Shared pytest fixtures and collection hooks."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest

from app.config import get_settings
from app.services.observability.bootstrap import reset_observability_for_tests
from app.services.observability.noop import NoopObservabilityAdapter


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-heavy",
        action="store_true",
        default=False,
        help="Include tests marked slow (eval soft/judge, live LLM smoke). Default: deselected.",
    )


def _include_heavy_tests(config: pytest.Config) -> bool:
    if config.getoption("--run-heavy"):
        return True
    raw = os.getenv("RUN_HEAVY_TESTS", "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    markexpr = (config.option.markexpr or "").strip()
    if markexpr == "slow":
        return True
    if "slow" in markexpr and "not slow" not in markexpr:
        return True
    return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _include_heavy_tests(config):
        return
    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if item.get_closest_marker("slow"):
            deselected.append(item)
        else:
            kept.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = kept


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


@pytest.fixture(autouse=True)
def stub_estimation_graph_checkpointer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real Postgres pool opens during TestClient lifespan (feature-066).

    Lifespan catches the failure and leaves ``app.state.graph = None``. Tests that
    exercise graph wiring override this fixture by re-patching ``open_checkpointer``.
    """

    @asynccontextmanager
    async def _stub_open_checkpointer(*_args, **_kwargs):
        raise RuntimeError("Postgres checkpointer disabled in default test suite")
        yield  # pragma: no cover

    monkeypatch.setattr(
        "app.services.estimation_graph.checkpointer.open_checkpointer",
        _stub_open_checkpointer,
    )
