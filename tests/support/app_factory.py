"""FastAPI harness for httpx-based integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app
from app.services.sessions import InMemorySessionStore
from tests.fakes.fake_llm_provider import FakeStructuredLLM
from tests.support.integration_settings import (
    integration_test_settings,
    session_integration_uses_real_llm,
)


def patch_session_stores(monkeypatch: pytest.MonkeyPatch, store: InMemorySessionStore) -> None:
    monkeypatch.setattr("app.services.sessions.session_store", store)
    monkeypatch.setattr("app.routers.sessions.session_store", store)


def install_fake_structured_llm(monkeypatch: pytest.MonkeyPatch, fake: FakeStructuredLLM) -> None:
    async def _complete_structured(**kwargs: object) -> object:
        return await fake.complete_structured(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "app.services.structured_llm_client.complete_structured",
        _complete_structured,
    )
    monkeypatch.setattr(
        "app.services.llm_service.complete_structured",
        _complete_structured,
    )
    monkeypatch.setattr(
        "app.guardrails.acb.orchestrator.complete_structured",
        _complete_structured,
    )


@asynccontextmanager
async def integration_async_client(
    *,
    monkeypatch: pytest.MonkeyPatch,
    store: InMemorySessionStore,
    fake: FakeStructuredLLM,
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides.clear()
    settings = integration_test_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    get_settings.cache_clear()
    patch_session_stores(monkeypatch, store)
    if not session_integration_uses_real_llm():
        install_fake_structured_llm(monkeypatch, fake)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()
