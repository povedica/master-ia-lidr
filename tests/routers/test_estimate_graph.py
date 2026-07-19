"""HTTP tests for the supervisor/worker estimation graph router (feature-067)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app import deps
from app.config import Settings
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


def _interrupt(gate: str = "estimation_review", **payload) -> SimpleNamespace:
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


def test_graph_start_returns_paused_awaiting_human_review(client: TestClient) -> None:
    paused = _snapshot(
        values={
            "status": "awaiting_human_review",
            "confidence": 0.42,
            "estimate": {"total_hours": 100.0},
            "validation": {
                "ok": False,
                "no_precedent": True,
                "review_reasons": ["no relevant historical precedent"],
            },
            "errors": [],
        },
        next_nodes=("human_review",),
        interrupts=(
            _interrupt(
                estimate={"total_hours": 100.0},
                confidence=0.42,
                review_reasons=["no relevant historical precedent"],
            ),
        ),
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
    assert body["status"] == "awaiting_human_review"
    assert body["confidence"] == 0.42
    assert body["pending_gate"]["gate"] == "estimation_review"
    assert "review_reasons" in body["pending_gate"]["payload"]
    graph.ainvoke.assert_awaited_once()


def test_graph_start_returns_completed_without_pause(client: TestClient) -> None:
    completed = _snapshot(
        values={
            "status": "completed",
            "confidence": 0.9,
            "estimate": {"total_hours": 160.0},
            "validation": {"ok": True, "review_reasons": []},
        },
        next_nodes=(),
    )
    graph = MagicMock()
    graph.ainvoke = AsyncMock()
    graph.aget_state = AsyncMock(return_value=completed)
    app.state.graph = graph

    response = client.post(
        GRAPH_PATH,
        json={"transcript": TRANSCRIPT, "estimation_id": "ok-1"},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "completed"
    assert body["status"] == "completed"
    assert body["pending_gate"] is None


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


def test_graph_resume_returns_404_for_unknown_id(client: TestClient) -> None:
    empty = _snapshot(values={}, next_nodes=(), created_at=None)
    graph = MagicMock()
    graph.ainvoke = AsyncMock()
    graph.aget_state = AsyncMock(return_value=empty)
    app.state.graph = graph

    response = client.post(
        f"{GRAPH_PATH}/missing/resume",
        json={"resolution": {"action": "approve"}},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 404
    graph.ainvoke.assert_not_awaited()


def test_graph_resume_returns_409_when_nothing_pending(client: TestClient) -> None:
    completed = _snapshot(
        values={"status": "completed", "estimate": {"total_hours": 10}},
        next_nodes=(),
    )
    graph = MagicMock()
    graph.ainvoke = AsyncMock()
    graph.aget_state = AsyncMock(return_value=completed)
    app.state.graph = graph

    response = client.post(
        f"{GRAPH_PATH}/e1/resume",
        json={"resolution": {"action": "approve"}},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 409
    graph.ainvoke.assert_not_awaited()


def test_graph_resume_rejects_invalid_resolution(client: TestClient) -> None:
    paused = _snapshot(
        values={"status": "awaiting_human_review"},
        next_nodes=("human_review",),
        interrupts=(_interrupt(),),
    )
    graph = MagicMock()
    graph.ainvoke = AsyncMock()
    graph.aget_state = AsyncMock(return_value=paused)
    app.state.graph = graph

    response = client.post(
        f"{GRAPH_PATH}/e1/resume",
        json={"resolution": {"action": "defer"}},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 422
    graph.ainvoke.assert_not_awaited()


@pytest.mark.parametrize(
    ("resolution", "final_status"),
    [
        ({"action": "approve", "comment": "ok"}, "completed"),
        (
            {
                "action": "adjust",
                "adjusted_estimate": {"total_hours": 90.0, "components": []},
            },
            "completed",
        ),
        ({"action": "reject", "comment": "no"}, "rejected"),
    ],
)
def test_graph_resume_approve_adjust_reject(
    client: TestClient,
    resolution: dict,
    final_status: str,
) -> None:
    paused = _snapshot(
        values={"status": "awaiting_human_review", "confidence": 0.3},
        next_nodes=("human_review",),
        interrupts=(_interrupt(),),
    )
    after = _snapshot(
        values={
            "status": final_status,
            "estimate": {"total_hours": 90.0},
            "human_resolution": resolution,
            "confidence": 0.3,
        },
        next_nodes=(),
    )
    graph = MagicMock()
    graph.ainvoke = AsyncMock()
    graph.aget_state = AsyncMock(side_effect=[paused, after])
    app.state.graph = graph

    response = client.post(
        f"{GRAPH_PATH}/e1/resume",
        json={"resolution": resolution},
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "completed"
    assert body["status"] == final_status
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
            "status": "completed",
            "confidence": 0.88,
            "estimate": {"total_hours": 120.0},
            "validation": {"ok": True},
            "requirements": [{"id": "req-1", "text": "API"}],
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
    assert body["status"] == "completed"
    assert body["confidence"] == 0.88
    assert body["requirements"][0]["id"] == "req-1"


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
        interrupts=(_interrupt(),),
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
    assert len(activity_log.read("stream-1")) == 2

    progress = client.get(
        f"{GRAPH_PATH}/stream-1/progress",
        headers={"X-API-Key": EST_KEY},
    )
    assert progress.status_code == 200
    body = progress.json()
    assert body["state"] == "paused"
    assert [e["node"] for e in body["activity"]] == ["supervisor", "requirements"]


def test_graph_resume_stream_returns_409_when_nothing_pending(
    client: TestClient,
) -> None:
    completed = _snapshot(
        values={"status": "completed", "estimate": {"total_hours": 10}},
        next_nodes=(),
    )
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=completed)
    graph.astream = MagicMock()
    app.state.graph = graph

    response = client.post(
        f"{GRAPH_PATH}/e1/resume-stream",
        json={"resolution": {"action": "approve"}},
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
        interrupts=(_interrupt(),),
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
            "estimate": {
                "total_hours": 96.0,
                "components": [{"name": "API", "estimated_hours": 96.0}],
            },
            "validation": {"ok": True, "summary": "estimate passed all guardrails"},
        },
        next_nodes=(),
    )
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=snap)
    app.state.graph = graph

    async def _fake_build_proposal(estimate, analysis_report, *, persona=None):
        del estimate, analysis_report, persona
        return CommercialProposal(
            title="Demo",
            executive_summary="Summary",
            scope=["API"],
            total_engineer_days=12,
            body_markdown="# Demo\n",
        )

    monkeypatch.setattr(
        "app.routers.estimate_graph.build_proposal",
        _fake_build_proposal,
    )
    monkeypatch.setattr(
        "app.routers.estimate_graph.get_settings",
        lambda: _settings_with_key(graph_proposal_enabled=True),
    )

    response = client.post(
        f"{GRAPH_PATH}/e1/proposal",
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Demo"
    assert body["total_engineer_days"] == 12


def test_graph_proposal_returns_409_without_estimate(client: TestClient) -> None:
    snap = _snapshot(values={"status": "running"}, next_nodes=("supervisor",))
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=snap)
    app.state.graph = graph

    response = client.post(
        f"{GRAPH_PATH}/e1/proposal",
        headers={"X-API-Key": EST_KEY},
    )
    assert response.status_code == 409


def test_graph_proposal_returns_503_when_disabled(client: TestClient) -> None:
    from app.config import get_settings

    app.dependency_overrides[get_settings] = lambda: _settings_with_key(
        graph_proposal_enabled=False
    )
    app.state.graph = MagicMock()
    try:
        response = client.post(
            f"{GRAPH_PATH}/e1/proposal",
            headers={"X-API-Key": EST_KEY},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert response.status_code == 503
