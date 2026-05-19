"""FastAPI harness for httpx-based integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.main import app
from app.services.sessions import InMemorySessionStore
from tests.fakes.fake_llm_provider import FakeStructuredLLM


def integration_test_settings() -> Settings:
    return Settings(
        openai_api_key="test-key",
        llm_domain_guardrail_enabled=False,
        semantic_cache_enabled=False,
        max_attachment_context_chars=8_000,
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
    install_fake_structured_llm(monkeypatch, fake)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()
