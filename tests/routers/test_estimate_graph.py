"""HTTP tests for the Session 13 estimation graph router (feature-066 Step 6)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.middleware import security

EST_KEY = "estimate-secret"
GRAPH_PATH = "/api/v1/estimate/graph"
TRANSCRIPT = "A" * 120


def _settings_with_key() -> Settings:
    return Settings(
        _env_file=None,
        estimate_api_key=EST_KEY,
        rate_limit_enabled=False,
    )


def _interrupt(gate: str = "structure_review", **payload) -> SimpleNamespace:
    return SimpleNamespace(
        value={"gate": gate, "estimation_id": "e1", **payload},
    )


def _snapshot(
    *,
    values: dict | None = None,
    next_nodes: tuple = (),
    interrupts: tuple = (),
    created_at: object | None = "2026-07-19T00:00:00Z",
) -> SimpleNamespace:
    return SimpleNamespace(
        values=values if values is not None else {},
        next=next_nodes,
        interrupts=interrupts,
        created_at=created_at,
    )


@pytest.fixture(autouse=True)
def _auth_and_no_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", _settings_with_key)
    yield


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_graph_start_returns_503_when_graph_unavailable(client: TestClient) -> None:
    assert app.state.graph is None
    response = client.post(
        GRAPH_PATH,
        json={"transcript": TRANSCRIPT},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 503
    assert "not available" in response.json()["detail"].lower()


def test_graph_start_requires_api_key(client: TestClient) -> None:
    app.state.graph = MagicMock()
    response = client.post(GRAPH_PATH, json={"transcript": TRANSCRIPT})
    assert response.status_code == 401


def test_graph_start_returns_paused_run_state(client: TestClient) -> None:
    paused = _snapshot(
        values={
            "complexity": "high",
            "structure": {"modules": [{"name": "Backend", "tasks": []}]},
            "errors": [],
        },
        next_nodes=("human_gate_structure",),
        interrupts=(_interrupt(structure={"modules": []}),),
    )
    graph = MagicMock()
    graph.ainvoke = AsyncMock()
    graph.aget_state = AsyncMock(return_value=paused)
    app.state.graph = graph

    response = client.post(
        GRAPH_PATH,
        json={"transcript": TRANSCRIPT, "estimation_id": "e1"},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["estimation_id"] == "e1"
    assert body["state"] == "paused"
    assert body["complexity"] == "high"
    assert body["pending_gate"]["gate"] == "structure_review"
    assert "structure" in body["pending_gate"]["payload"]
    graph.ainvoke.assert_awaited_once()


def test_graph_start_returns_502_on_graph_failure(client: TestClient) -> None:
    graph = MagicMock()
    graph.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))
    graph.aget_state = AsyncMock()
    app.state.graph = graph

    response = client.post(
        GRAPH_PATH,
        json={"transcript": TRANSCRIPT},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 502
    assert "Failed to produce" in response.json()["detail"]


def test_graph_resume_returns_409_when_nothing_pending(client: TestClient) -> None:
    completed = _snapshot(
        values={"status": "validated", "estimate": {"total_engineer_days": 10}},
        next_nodes=(),
    )
    graph = MagicMock()
    graph.ainvoke = AsyncMock()
    graph.aget_state = AsyncMock(return_value=completed)
    app.state.graph = graph

    response = client.post(
        f"{GRAPH_PATH}/e1/resume",
        json={"decision": {"approved": True}},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 409
    graph.ainvoke.assert_not_awaited()


def test_graph_resume_continues_paused_run(client: TestClient) -> None:
    paused = _snapshot(
        values={"complexity": "medium"},
        next_nodes=("human_gate_structure",),
        interrupts=(_interrupt(),),
    )
    after = _snapshot(
        values={
            "complexity": "medium",
            "estimate": {"total_engineer_days": 5},
            "analysis_report": {"overall_confidence": "medium"},
        },
        next_nodes=("human_gate_analysis",),
        interrupts=(_interrupt(gate="final_review", estimate={}),),
    )
    graph = MagicMock()
    graph.ainvoke = AsyncMock()
    graph.aget_state = AsyncMock(side_effect=[paused, after])
    app.state.graph = graph

    response = client.post(
        f"{GRAPH_PATH}/e1/resume",
        json={"decision": {"approved": True}},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "paused"
    assert body["pending_gate"]["gate"] == "final_review"
    assert body["estimate"]["total_engineer_days"] == 5
    graph.ainvoke.assert_awaited_once()


def test_graph_state_returns_404_for_unknown_id(client: TestClient) -> None:
    empty = _snapshot(values={}, next_nodes=(), created_at=None)
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=empty)
    app.state.graph = graph

    response = client.get(
        f"{GRAPH_PATH}/missing/state",
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 404


def test_graph_state_returns_snapshot(client: TestClient) -> None:
    snap = _snapshot(
        values={
            "complexity": "low",
            "status": "validated",
            "proposal": "# Proposal\n...",
            "task_hours": [{"module": "Backend", "task": "API"}],
        },
        next_nodes=(),
    )
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=snap)
    app.state.graph = graph

    response = client.get(
        f"{GRAPH_PATH}/e1/state",
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "completed"
    assert body["status"] == "validated"
    assert body["proposal"].startswith("# Proposal")
    assert len(body["task_hours"]) == 1


def test_graph_rejects_short_transcript(client: TestClient) -> None:
    app.state.graph = MagicMock()
    response = client.post(
        GRAPH_PATH,
        json={"transcript": "too short"},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 422
