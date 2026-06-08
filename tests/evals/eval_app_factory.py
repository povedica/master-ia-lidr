"""Eval-specific ASGI harness with eval settings and optional fake LLM."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app
from app.services.sessions import InMemorySessionStore
from tests.evals.fakes import EvalStructuredLLM
from tests.evals.settings import eval_estimator_uses_real_llm, eval_test_settings
from tests.support.app_factory import install_fake_structured_llm, patch_session_stores


@asynccontextmanager
async def eval_integration_client(
    *,
    monkeypatch: pytest.MonkeyPatch,
    store: InMemorySessionStore,
    fake: EvalStructuredLLM,
    force_fake: bool = False,
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides.clear()
    settings = eval_test_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    get_settings.cache_clear()
    patch_session_stores(monkeypatch, store)
    use_fake = force_fake or not eval_estimator_uses_real_llm()
    if use_fake:
        install_fake_structured_llm(monkeypatch, fake)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()
