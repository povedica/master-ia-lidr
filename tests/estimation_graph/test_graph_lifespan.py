"""Lifespan wiring for the estimation graph (feature-066 Step 5).

Asserts resilient startup: checkpointer/graph failure leaves ``app.state.graph``
as ``None`` while ``/health`` and the rest of the API stay up.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from app.config import Settings, get_settings
from app.main import app
from app.services.observability.bootstrap import reset_observability_for_tests


@pytest.fixture(autouse=True)
def _reset_observability() -> None:
    reset_observability_for_tests()
    yield
    reset_observability_for_tests()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_lifespan_sets_graph_none_when_checkpointer_fails() -> None:
    @asynccontextmanager
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("postgres unreachable")
        yield  # pragma: no cover

    fake_obs = MagicMock()
    with (
        patch(
            "app.services.estimation_graph.checkpointer.open_checkpointer",
            _boom,
        ),
        patch(
            "app.services.observability.bootstrap.build_observability_adapter",
            return_value=fake_obs,
        ),
        patch(
            "app.main.get_settings",
            return_value=Settings(
                _env_file=None,
                database_url="postgresql+asyncpg://u:p@127.0.0.1:5432/db",
            ),
        ),
    ):
        with TestClient(app) as client:
            assert app.state.graph is None
            response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_builds_graph_when_checkpointer_ready() -> None:
    @asynccontextmanager
    async def _memory_checkpointer(*_args, **_kwargs):
        yield MemorySaver()

    fake_obs = MagicMock()
    with (
        patch(
            "app.services.estimation_graph.checkpointer.open_checkpointer",
            _memory_checkpointer,
        ),
        patch(
            "app.services.observability.bootstrap.build_observability_adapter",
            return_value=fake_obs,
        ),
        patch(
            "app.main.get_settings",
            return_value=Settings(
                _env_file=None,
                database_url="postgresql+asyncpg://u:p@127.0.0.1:5432/db",
            ),
        ),
    ):
        with TestClient(app) as client:
            assert app.state.graph is not None
            response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_skips_graph_when_database_url_empty() -> None:
    fake_obs = MagicMock()
    open_cp = MagicMock()
    with (
        patch(
            "app.services.estimation_graph.checkpointer.open_checkpointer",
            open_cp,
        ),
        patch(
            "app.services.observability.bootstrap.build_observability_adapter",
            return_value=fake_obs,
        ),
        patch(
            "app.main.get_settings",
            return_value=Settings(_env_file=None, database_url=""),
        ),
    ):
        with TestClient(app) as client:
            assert app.state.graph is None
            response = client.get("/health")

    open_cp.assert_not_called()
    assert response.status_code == 200
