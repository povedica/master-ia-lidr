"""Unit tests for Session 14 CLI helpers (feature-067)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings
from app.scripts.run_graph_s13 import (
    GATE_DECISIONS,
    install_stub_workers,
    render_run,
    run_to_completion,
)
from app.services.estimation_graph.build import build_graph


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_gate_decisions_cover_estimation_review() -> None:
    assert GATE_DECISIONS["estimation_review"]["action"] == "approve"


def test_render_run_includes_supervisor_artifacts() -> None:
    text = render_run(
        {
            "estimation_id": "s14-demo",
            "status": "completed",
            "confidence": 0.42,
            "last_route": "END",
            "route_reason": "human_approved",
            "requirements": [
                {"id": "req-1", "text": "Quantum dashboard", "category": "r&d"}
            ],
            "budget_matches": [
                {
                    "requirement_id": "req-1",
                    "reference_budget_id": None,
                    "amount": 0.0,
                    "distance": 1.0,
                    "no_match": True,
                }
            ],
            "estimate": {
                "components": [
                    {
                        "name": "Quantum dashboard",
                        "estimated_hours": 0.0,
                        "unbudgeted": True,
                    }
                ],
                "total_hours": 0.0,
            },
            "validation": {
                "ok": False,
                "no_precedent": True,
                "review_reasons": ["no relevant historical precedent"],
            },
            "human_resolution": {"action": "approve"},
            "supervisor_decisions": [
                {"goto": "human_review", "reason": "human_review_required"}
            ],
        }
    )
    assert "s14-demo" in text
    assert "Quantum dashboard" in text
    assert "NO MATCH" in text
    assert "no relevant historical precedent" in text
    assert "human_review" in text


@pytest.mark.asyncio
async def test_run_to_completion_auto_approves_estimation_review() -> None:
    stubs = install_stub_workers()
    graph = build_graph(MemorySaver(), **stubs)
    state = await run_to_completion(graph, "A" * 200, "cli-e2e")

    assert state.get("status") == "completed"
    assert state.get("human_resolution", {}).get("action") == "approve"
    assert state.get("search_attempted") is True
    assert any(row.get("no_match") for row in state.get("budget_matches") or [])

    snapshot = await graph.aget_state({"configurable": {"thread_id": "cli-e2e"}})
    assert not snapshot.next
