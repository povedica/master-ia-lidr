"""Integration tests for session estimate ACB orchestration."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.main import app
from app.schemas.acb.boss import BossAction
from tests.fakes.fake_llm_provider import FakeStructuredLLM
from tests.fixtures.transcripts import TURN_1
from tests.support.app_factory import integration_async_client, patch_session_stores
from tests.support.integration_settings import integration_test_settings
from tests.support.session_integration_markers import requires_fake_structured_llm

pytest_plugins = ["tests.fixtures.conftest_sessions"]


@pytest.fixture
async def acb_async_client(
    session_store,
    fake_structured_llm: FakeStructuredLLM,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = integration_test_settings().model_copy(
        update={
            "acb_enabled": True,
            "dev_mode": True,
        }
    )
    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: settings
    get_settings.cache_clear()
    patch_session_stores(monkeypatch, session_store)
    from tests.support.app_factory import install_fake_structured_llm

    install_fake_structured_llm(monkeypatch, fake_structured_llm)
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.mark.asyncio
@requires_fake_structured_llm
async def test_session_acb_happy_accept(
    acb_async_client: AsyncClient,
    fake_structured_llm: FakeStructuredLLM,
) -> None:
    fake_structured_llm.acb_boss_action = BossAction.accept
    created = await acb_async_client.post("/api/v1/sessions")
    session_id = created.json()["session_id"]

    response = await acb_async_client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        json=TURN_1,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["estimate"]["result"]["title"]
    assert body["estimate"].get("acb_trace") is not None
    assert body["estimate"]["acb_trace"]["final_path"] == "accept"
    assert fake_structured_llm.calls


@pytest.mark.asyncio
@requires_fake_structured_llm
async def test_session_single_pass_disables_acb(
    acb_async_client: AsyncClient,
    fake_structured_llm: FakeStructuredLLM,
) -> None:
    fake_structured_llm.reset()
    created = await acb_async_client.post("/api/v1/sessions")
    session_id = created.json()["session_id"]
    payload = dict(TURN_1)
    payload["orchestration"] = "single_pass"

    response = await acb_async_client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        json=payload,
    )
    assert response.status_code == 200
    assert response.json()["estimate"].get("acb_trace") is None
    critic_calls = [c for c in fake_structured_llm.calls if c.response_model.__name__ == "CriticFeedback"]
    assert critic_calls == []
