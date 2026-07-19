"""HTTP tests for the Session 13 estimation graph router (feature-066 Steps 6–8)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app import deps
from app.config import Settings, get_settings
from app.main import app
from app.middleware import security
from app.services.estimation_graph.activity import GraphActivityLog
from app.services.estimation_graph.schemas import CommercialProposal

EST_KEY = "estimate-secret"
GRAPH_PATH = "/api/v1/estimate/graph"
TRANSCRIPT = "A" * 120


def _settings_with_key(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        estimate_api_key=EST_KEY,
        rate_limit_enabled=False,
        **overrides,
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
def activity_log() -> GraphActivityLog:
    return GraphActivityLog(redis_client=None)


@pytest.fixture
def client(activity_log: GraphActivityLog) -> TestClient:
    deps.get_graph_activity.cache_clear()
    app.dependency_overrides[deps.get_graph_activity] = lambda: activity_log
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(deps.get_graph_activity, None)
    deps.get_graph_activity.cache_clear()


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


def test_graph_stream_returns_202_and_progress_shows_activity(
    client: TestClient,
    activity_log: GraphActivityLog,
) -> None:
    paused = _snapshot(
        values={"status": "awaiting_human_review", "confidence": 0.4, "errors": []},
        next_nodes=("human_review",),
        interrupts=(_interrupt(gate="estimation_review"),),
    )

    async def _astream(_payload, _config, stream_mode="updates"):  # noqa: ARG001
        yield {
            "supervisor": {
                "last_route": "requirements_extractor",
                "route_reason": "missing_requirements",
            }
        }
        yield {
            "requirements_extractor": {
                "requirements": [{"id": "req-1", "text": "API"}],
            }
        }

    graph = MagicMock()
    graph.astream = _astream
    graph.aget_state = AsyncMock(return_value=paused)
    app.state.graph = graph

    start = client.post(
        f"{GRAPH_PATH}/stream",
        json={"transcript": TRANSCRIPT, "estimation_id": "stream-1"},
        headers={"X-API-Key": EST_KEY},
    )
    assert start.status_code == 202
    assert start.json()["state"] == "running"
    assert start.json()["estimation_id"] == "stream-1"
    # TestClient runs BackgroundTasks before returning.
    assert len(activity_log.read("stream-1")) == 2

    progress = client.get(
        f"{GRAPH_PATH}/stream-1/progress",
        headers={"X-API-Key": EST_KEY},
    )
    assert progress.status_code == 200
    body = progress.json()
    assert body["state"] == "paused"
    assert [e["node"] for e in body["activity"]] == ["supervisor", "requirements"]
    assert "requirements_extractor" in body["activity"][0]["message"]


def test_graph_resume_stream_returns_409_when_nothing_pending(
    client: TestClient,
) -> None:
    completed = _snapshot(
        values={"status": "validated", "estimate": {"total_engineer_days": 10}},
        next_nodes=(),
    )
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=completed)
    graph.astream = MagicMock()
    app.state.graph = graph

    response = client.post(
        f"{GRAPH_PATH}/e1/resume-stream",
        json={"decision": {"approved": True}},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 409


def test_graph_resume_stream_returns_202(
    client: TestClient,
    activity_log: GraphActivityLog,
) -> None:
    paused = _snapshot(
        values={"status": "awaiting_human_review", "confidence": 0.4},
        next_nodes=("human_review",),
        interrupts=(_interrupt(gate="estimation_review"),),
    )
    after = _snapshot(
        values={
            "status": "completed",
            "estimate": {"total_hours": 120.0},
            "confidence": 0.4,
        },
        next_nodes=(),
    )

    async def _astream(_payload, _config, stream_mode="updates"):  # noqa: ARG001
        yield {"estimate_generator": {"estimate": {"total_hours": 120.0}}}

    graph = MagicMock()
    graph.astream = _astream
    graph.aget_state = AsyncMock(side_effect=[paused, after])
    app.state.graph = graph

    response = client.post(
        f"{GRAPH_PATH}/e1/resume-stream",
        json={"resolution": {"action": "approve"}},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 202
    assert response.json()["state"] == "running"
    assert activity_log.read("e1")
    assert "120.0h" in activity_log.read("e1")[0]["message"]


def test_graph_proposal_returns_draft(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snap = _snapshot(
        values={
            "estimate": {"total_engineer_days": 12, "modules": []},
            "analysis_report": {"summary": "ok"},
        },
        next_nodes=(),
    )
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=snap)
    app.state.graph = graph
    app.dependency_overrides[get_settings] = lambda: _settings_with_key()

    async def _fake_build_proposal(estimate, analysis_report, *, persona=None):  # noqa: ARG001
        return CommercialProposal(
            title="Demo",
            executive_summary="Summary",
            scope=["Backend"],
            total_engineer_days=12,
            body_markdown="# Proposal\nBody",
        )

    monkeypatch.setattr(
        "app.routers.estimate_graph.build_proposal",
        _fake_build_proposal,
    )

    try:
        response = client.post(
            f"{GRAPH_PATH}/e1/proposal",
            headers={"X-API-Key": EST_KEY},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    body = response.json()
    assert body["estimation_id"] == "e1"
    assert body["title"] == "Demo"
    assert body["total_engineer_days"] == 12
    assert body["body_markdown"].startswith("# Proposal")


def test_graph_proposal_returns_409_without_estimate(client: TestClient) -> None:
    snap = _snapshot(values={"complexity": "low"}, next_nodes=())
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=snap)
    app.state.graph = graph
    app.dependency_overrides[get_settings] = lambda: _settings_with_key()

    try:
        response = client.post(
            f"{GRAPH_PATH}/e1/proposal",
            headers={"X-API-Key": EST_KEY},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 409


def test_graph_proposal_returns_503_when_disabled(client: TestClient) -> None:
    app.state.graph = MagicMock()
    app.dependency_overrides[get_settings] = lambda: _settings_with_key(
        graph_proposal_enabled=False
    )
    try:
        response = client.post(
            f"{GRAPH_PATH}/e1/proposal",
            headers={"X-API-Key": EST_KEY},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert response.status_code == 503


def test_graph_stream_requires_api_key(client: TestClient) -> None:
    app.state.graph = MagicMock()
    response = client.post(
        f"{GRAPH_PATH}/stream",
        json={"transcript": TRANSCRIPT},
    )
    assert response.status_code == 401
