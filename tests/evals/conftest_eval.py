"""Pytest fixtures for eval HTTP harness (separate from session integration)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from app.services.sessions import InMemorySessionStore
from tests.evals.eval_app_factory import eval_integration_client
from tests.evals.fakes import EvalStructuredLLM


@pytest.fixture
def eval_session_store() -> InMemorySessionStore:
    store = InMemorySessionStore()
    yield store
    store.reset_for_tests()


@pytest.fixture
def eval_structured_llm() -> EvalStructuredLLM:
    fake = EvalStructuredLLM()
    yield fake
    fake.reset()
    fake.clear_success_criteria()


@pytest.fixture
async def eval_async_client(
    eval_session_store: InMemorySessionStore,
    eval_structured_llm: EvalStructuredLLM,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """Deterministic harness: always uses the golden-aligned fake structured LLM."""

    async with eval_integration_client(
        monkeypatch=monkeypatch,
        store=eval_session_store,
        fake=eval_structured_llm,
        force_fake=True,
    ) as client:
        yield client


@pytest.fixture
async def eval_live_async_client(
    eval_session_store: InMemorySessionStore,
    eval_structured_llm: EvalStructuredLLM,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """Live-estimator harness for soft/judge evals (respects ``EVAL_ESTIMATOR_USE_REAL_LLM``)."""

    async with eval_integration_client(
        monkeypatch=monkeypatch,
        store=eval_session_store,
        fake=eval_structured_llm,
        force_fake=False,
    ) as client:
        yield client
