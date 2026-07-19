"""Routing helpers for the estimation graph (feature-066 Step 3)."""

from __future__ import annotations

import pytest
from langgraph.types import Send

from app.config import get_settings
from app.services.estimation_graph.build import fan_out_hours, route_after_gate2


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_fan_out_hours_emits_one_send_per_task() -> None:
    state = {
        "approved_modules": [
            {
                "name": "Auth",
                "tasks": [
                    {"name": "OAuth", "description": "tokens"},
                    {"name": "RBAC"},
                ],
            },
            {"name": "Reporting", "tasks": [{"name": "Dashboards"}]},
        ]
    }
    sends = fan_out_hours(state)
    assert isinstance(sends, list)
    assert len(sends) == 3
    assert all(isinstance(item, Send) for item in sends)
    assert {item.node for item in sends} == {"estimate_task_hours"}
    payloads = {(item.arg["module"], item.arg["task"]) for item in sends}
    assert payloads == {
        ("Auth", "OAuth"),
        ("Auth", "RBAC"),
        ("Reporting", "Dashboards"),
    }


def test_fan_out_hours_with_no_tasks_routes_to_join() -> None:
    assert fan_out_hours({"approved_modules": []}) == "recover_and_handover"
    assert fan_out_hours({}) == "recover_and_handover"


def test_route_after_gate2_honours_want_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPH_PROPOSAL_ENABLED", "true")
    get_settings.cache_clear()
    assert route_after_gate2({"gate2_decision": {"want_proposal": True}}) == "proposal"
    assert route_after_gate2({"gate2_decision": {"want_proposal": False}}) == "end"
    assert route_after_gate2({}) == "end"


def test_route_after_gate2_skips_proposal_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_PROPOSAL_ENABLED", "false")
    get_settings.cache_clear()
    assert route_after_gate2({"gate2_decision": {"want_proposal": True}}) == "end"
