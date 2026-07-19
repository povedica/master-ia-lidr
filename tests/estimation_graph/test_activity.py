"""Activity feed helpers for supervisor/worker stream mode — network-free."""

from __future__ import annotations

from app.services.estimation_graph.activity import GraphActivityLog, describe_node


def test_describe_supervisor_reads_route() -> None:
    lines = describe_node(
        "supervisor",
        {"last_route": "budget_searcher", "route_reason": "historical_search_pending"},
    )
    assert lines == [
        {
            "node": "supervisor",
            "label": "Supervisor",
            "message": "Ruta → budget_searcher (historical_search_pending)",
        }
    ]


def test_describe_requirements_counts() -> None:
    update = {"requirements": [{"id": "req-1"}, {"id": "req-2"}]}
    (line,) = describe_node("requirements_extractor", update)
    assert line["node"] == "requirements"
    assert line["message"] == "2 requisitos extraídos"


def test_describe_budget_search_counts_no_match() -> None:
    update = {
        "budget_matches": [
            {"no_match": True},
            {"no_match": False, "reference_budget_id": "b1"},
        ]
    }
    (line,) = describe_node("budget_searcher", update)
    assert line["node"] == "budget_search"
    assert "2 filas" in line["message"]
    assert "1 sin precedente" in line["message"]


def test_describe_estimate_total_hours() -> None:
    (line,) = describe_node("estimate_generator", {"estimate": {"total_hours": 184.0}})
    assert line["node"] == "estimate"
    assert "184.0h" in line["message"]


def test_describe_validator_confidence_and_reasons() -> None:
    update = {
        "confidence": 0.35,
        "validation": {"review_reasons": ["no relevant historical precedent"]},
    }
    (line,) = describe_node("coherence_validator", update)
    assert line["node"] == "validator"
    assert "0.35" in line["message"]
    assert "1 señales HITL" in line["message"]


def test_describe_human_review_action() -> None:
    (line,) = describe_node(
        "human_review",
        {"human_resolution": {"action": "approve"}},
    )
    assert line["node"] == "human_review"
    assert "approve" in line["message"]


def test_describe_interrupt_and_unknown_never_raise() -> None:
    assert describe_node("__interrupt__", None)[0]["message"].startswith("⏸")
    assert describe_node("mystery_node", {"weird": 1})[0]["node"] == "mystery_node"


def test_activity_log_in_process_fallback_appends_reads_and_resets() -> None:
    log = GraphActivityLog(redis_client=None)
    log.append("run-1", node="supervisor", label="Supervisor", message="Ruta → END")
    log.append(
        "run-1",
        node="validator",
        label="Validator",
        message="Confianza 0.9",
    )
    entries = log.read("run-1")
    assert [e["seq"] for e in entries] == [0, 1]
    assert entries[1]["node"] == "validator"
    assert log.read("run-2") == []
    log.reset("run-1")
    assert log.read("run-1") == []
