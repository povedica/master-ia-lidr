"""Unit tests for pooled AsyncPostgresSaver wiring (feature-066 Step 5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings, get_settings
from app.services.estimation_graph.checkpointer import open_checkpointer


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_open_checkpointer_opens_pool_setup_and_closes() -> None:
    pool = MagicMock()
    pool.open = AsyncMock()
    pool.close = AsyncMock()
    saver = MagicMock()
    saver.setup = AsyncMock()

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://estimator:secret@127.0.0.1:5432/estimator",
    )

    with (
        patch(
            "app.services.estimation_graph.checkpointer.get_settings",
            return_value=settings,
        ),
        patch(
            "app.services.estimation_graph.checkpointer.AsyncConnectionPool",
            return_value=pool,
        ) as pool_cls,
        patch(
            "app.services.estimation_graph.checkpointer.AsyncPostgresSaver",
            return_value=saver,
        ) as saver_cls,
    ):
        async with open_checkpointer() as checkpointer:
            assert checkpointer is saver

    pool_cls.assert_called_once()
    kwargs = pool_cls.call_args.kwargs
    assert kwargs["conninfo"] == "postgresql://estimator:secret@127.0.0.1:5432/estimator"
    assert kwargs["open"] is False
    assert kwargs["min_size"] == 1
    assert kwargs["max_size"] == 10
    pool.open.assert_awaited_once_with(wait=True)
    saver_cls.assert_called_once_with(pool)
    saver.setup.assert_awaited_once()
    pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_open_checkpointer_closes_pool_when_setup_fails() -> None:
    pool = MagicMock()
    pool.open = AsyncMock()
    pool.close = AsyncMock()
    saver = MagicMock()
    saver.setup = AsyncMock(side_effect=RuntimeError("setup boom"))

    settings = Settings(
        _env_file=None,
        database_url="postgresql://estimator:secret@127.0.0.1:5432/estimator",
    )

    with (
        patch(
            "app.services.estimation_graph.checkpointer.get_settings",
            return_value=settings,
        ),
        patch(
            "app.services.estimation_graph.checkpointer.AsyncConnectionPool",
            return_value=pool,
        ),
        patch(
            "app.services.estimation_graph.checkpointer.AsyncPostgresSaver",
            return_value=saver,
        ),
    ):
        with pytest.raises(RuntimeError, match="setup boom"):
            async with open_checkpointer():
                pass  # pragma: no cover

    pool.close.assert_awaited_once()
