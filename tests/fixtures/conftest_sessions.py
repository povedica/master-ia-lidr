"""Pytest fixtures for session integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from app.services.sessions import InMemorySessionStore
from tests.fakes.fake_llm_provider import FakeStructuredLLM
from tests.support.app_factory import integration_async_client


@pytest.fixture
def session_store() -> InMemorySessionStore:
    store = InMemorySessionStore()
    yield store
    store.reset_for_tests()


@pytest.fixture
def fake_structured_llm() -> FakeStructuredLLM:
    fake = FakeStructuredLLM()
    yield fake
    fake.reset()


@pytest.fixture
async def async_client(
    session_store: InMemorySessionStore,
    fake_structured_llm: FakeStructuredLLM,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    async with integration_async_client(
        monkeypatch=monkeypatch,
        store=session_store,
        fake=fake_structured_llm,
    ) as client:
        yield client
