"""Unit tests for LangGraph checkpointer DSN derivation (feature-066)."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings
from app.services.estimation_graph.checkpointer import saver_conninfo


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_saver_conninfo_strips_asyncpg_driver() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://estimator:secret@127.0.0.1:5432/estimator",
    )
    assert (
        saver_conninfo(settings)
        == "postgresql://estimator:secret@127.0.0.1:5432/estimator"
    )


def test_saver_conninfo_strips_psycopg_driver() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://estimator:secret@db/estimator",
    )
    assert saver_conninfo(settings) == "postgresql://estimator:secret@db/estimator"


def test_saver_conninfo_leaves_plain_libpq_dsn() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://estimator:secret@localhost/estimator",
    )
    assert saver_conninfo(settings) == "postgresql://estimator:secret@localhost/estimator"
