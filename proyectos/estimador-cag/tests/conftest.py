"""Shared pytest fixtures."""

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    """Avoid stale Settings between tests that tweak environment variables."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
