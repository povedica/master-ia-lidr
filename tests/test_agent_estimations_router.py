"""Tests for agentic estimation HTTP API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_db_session
from app.main import app
from app.routers import agent_estimations
from app.services.agentic.agent_schemas import (
    AgentComponent,
    AgentEstimate,
    AgentRunResult,
    AgentStep,
    AgentTrace,
)

AGENT_PATH = "/api/v1/estimate/agent"


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _session_override():
    session = AsyncMock()
    yield session


def test_agent_estimate_returns_503_without_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app.dependency_overrides[get_db_session] = _session_override
    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                AGENT_PATH,
                json={"transcript": "We need a backend and a mobile app."},
            )
        assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_agent_estimate_returns_trace_and_estimate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_result = AgentRunResult(
        estimate=AgentEstimate(
            components=[
                AgentComponent(name="Backend", estimated_hours=100.0, rationale="grounded")
            ],
            total_hours=100.0,
            confidence="medium",
        ),
        trace=AgentTrace(
            steps=[
                AgentStep(
                    step=1,
                    reasoning_summary="search",
                    tool="search_budgets",
                    tool_args={"query": "backend"},
                    observation="1 item",
                )
            ]
        ),
        iterations=2,
        stopped_reason="completed",
    )

    app.dependency_overrides[get_db_session] = _session_override
    try:
        with (
            patch(
                "app.routers.agent_estimations.run_estimation_agent",
                new=AsyncMock(return_value=fake_result),
            ),
            patch(
                "app.routers.agent_estimations.get_async_openai_client",
                return_value=MagicMock(),
            ),
            patch(
                "app.routers.agent_estimations.build_retrieval_backend",
                return_value=AsyncMock(),
            ),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                AGENT_PATH,
                json={"transcript": "We need a backend."},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["stopped_reason"] == "completed"
    assert body["result"]["total_hours"] == 100.0
    assert len(body["trace"]["steps"]) == 1
