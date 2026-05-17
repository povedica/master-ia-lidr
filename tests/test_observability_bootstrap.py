"""Observability bootstrap and FastAPI lifespan integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.services.observability.bootstrap import (
    get_observability,
    init_observability,
    reset_observability_for_tests,
    shutdown_observability,
)


def test_init_observability_returns_singleton_instance() -> None:
    reset_observability_for_tests()
    fake = MagicMock()
    settings = Settings(_env_file=None)
    with patch(
        "app.services.observability.bootstrap.build_observability_adapter",
        return_value=fake,
    ) as build:
        first = init_observability(settings)
        second = get_observability()
        third = init_observability(settings)

    build.assert_called_once_with(settings)
    assert first is fake
    assert second is fake
    assert third is fake


def test_shutdown_observability_flushes_adapter() -> None:
    reset_observability_for_tests()
    fake = MagicMock()
    with patch(
        "app.services.observability.bootstrap.build_observability_adapter",
        return_value=fake,
    ):
        init_observability(Settings(_env_file=None))
        shutdown_observability()

    fake.flush.assert_called_once()


def test_app_lifespan_flushes_observability_on_shutdown() -> None:
    reset_observability_for_tests()
    fake = MagicMock()
    with patch(
        "app.services.observability.bootstrap.build_observability_adapter",
        return_value=fake,
    ):
        with TestClient(app) as client:
            response = client.get("/health")
        assert response.status_code == 200

    fake.flush.assert_called_once()
