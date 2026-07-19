"""Supervisor routing matrix (feature-067)."""

from __future__ import annotations

from langgraph.graph import END
from langgraph.types import Command

from app.services.estimation_graph.supervisor import supervisor


def _goto(command: Command) -> str | object:
    return command.goto


def test_missing_requirements_routes_to_extractor() -> None:
    result = supervisor({"transcript": "x" * 120, "status": "running"})
    assert isinstance(result, Command)
    assert _goto(result) == "requirements_extractor"
    assert result.update["route_reason"] == "missing_requirements"
    assert result.update["last_route"] == "requirements_extractor"


def test_requirements_present_routes_to_budget_searcher() -> None:
    result = supervisor(
        {
            "requirements": [{"id": "r1", "text": "API"}],
            "search_attempted": False,
            "completed_workers": ["requirements_extractor"],
        }
    )
    assert _goto(result) == "budget_searcher"
    assert result.update["route_reason"] == "historical_search_pending"


def test_empty_search_completed_routes_to_estimate_generator() -> None:
    result = supervisor(
        {
            "requirements": [{"id": "r1", "text": "API"}],
            "search_attempted": True,
            "budget_matches": [
                {
                    "requirement_id": "r1",
                    "reference_budget_id": None,
                    "no_match": True,
                    "amount": 0.0,
                    "distance": 1.0,
                    "component": "API",
                }
            ],
            "completed_workers": ["requirements_extractor", "budget_searcher"],
        }
    )
    assert _goto(result) == "estimate_generator"
    assert result.update["route_reason"] == "estimation_pending"


def test_estimate_present_routes_to_coherence_validator() -> None:
    result = supervisor(
        {
            "requirements": [{"id": "r1"}],
            "search_attempted": True,
            "estimate": {"total_hours": 100.0, "components": []},
            "completed_workers": [
                "requirements_extractor",
                "budget_searcher",
                "estimate_generator",
            ],
        }
    )
    assert _goto(result) == "coherence_validator"
    assert result.update["route_reason"] == "validation_pending"


def test_clean_validation_ends_completed() -> None:
    result = supervisor(
        {
            "requirements": [{"id": "r1"}],
            "search_attempted": True,
            "estimate": {"total_hours": 100.0},
            "validation": {
                "ok": True,
                "out_of_historical_range": False,
                "no_precedent": False,
                "review_reasons": [],
            },
            "confidence": 0.9,
            "completed_workers": [
                "requirements_extractor",
                "budget_searcher",
                "estimate_generator",
                "coherence_validator",
            ],
        }
    )
    assert _goto(result) == END
    assert result.update["status"] == "completed"
    assert result.update["route_reason"] == "validation_passed"


def test_review_signals_route_to_human_review() -> None:
    result = supervisor(
        {
            "requirements": [{"id": "r1"}],
            "search_attempted": True,
            "estimate": {"total_hours": 100.0},
            "validation": {
                "ok": False,
                "out_of_historical_range": False,
                "no_precedent": True,
                "review_reasons": ["no relevant historical precedent"],
            },
            "confidence": 0.4,
            "completed_workers": [
                "requirements_extractor",
                "budget_searcher",
                "estimate_generator",
                "coherence_validator",
            ],
        }
    )
    assert _goto(result) == "human_review"
    assert result.update["route_reason"] == "human_review_required"
    assert result.update["status"] == "awaiting_human_review"


def test_approve_resolution_ends_completed() -> None:
    result = supervisor(
        {
            "requirements": [{"id": "r1"}],
            "search_attempted": True,
            "estimate": {"total_hours": 100.0},
            "validation": {"ok": False, "no_precedent": True, "review_reasons": ["x"]},
            "confidence": 0.4,
            "human_resolution": {"action": "approve", "comment": "ok"},
            "completed_workers": [
                "requirements_extractor",
                "budget_searcher",
                "estimate_generator",
                "coherence_validator",
            ],
        }
    )
    assert _goto(result) == END
    assert result.update["status"] == "completed"
    assert result.update["route_reason"] == "human_approved"


def test_reject_resolution_ends_rejected() -> None:
    result = supervisor(
        {
            "estimate": {"total_hours": 100.0},
            "validation": {"ok": False, "review_reasons": ["x"]},
            "confidence": 0.2,
            "human_resolution": {"action": "reject", "comment": "no"},
            "search_attempted": True,
            "requirements": [{"id": "r1"}],
        }
    )
    assert _goto(result) == END
    assert result.update["status"] == "rejected"
    assert result.update["route_reason"] == "human_rejected"


def test_adjust_resolution_routes_to_validator_once() -> None:
    result = supervisor(
        {
            "requirements": [{"id": "r1"}],
            "search_attempted": True,
            "estimate": {"total_hours": 120.0},
            "validation": {"ok": False, "review_reasons": ["x"]},
            "confidence": 0.2,
            "human_resolution": {
                "action": "adjust",
                "adjusted_estimate": {"total_hours": 90.0, "components": []},
            },
            "human_adjustment_validated": False,
        }
    )
    assert _goto(result) == "coherence_validator"
    assert result.update["route_reason"] == "human_adjusted_revalidate"
    assert result.update["human_adjustment_validated"] is False


def test_adjusted_after_revalidation_ends_without_review_loop() -> None:
    result = supervisor(
        {
            "requirements": [{"id": "r1"}],
            "search_attempted": True,
            "estimate": {"total_hours": 90.0},
            "validation": {
                "ok": False,
                "no_precedent": True,
                "review_reasons": ["no relevant historical precedent"],
            },
            "confidence": 0.3,
            "human_resolution": {
                "action": "adjust",
                "adjusted_estimate": {"total_hours": 90.0},
            },
            "human_adjustment_validated": True,
        }
    )
    assert _goto(result) == END
    assert result.update["status"] == "completed"
    assert result.update["route_reason"] == "human_adjusted_finalized"


def test_supervisor_update_includes_decision_record() -> None:
    result = supervisor({"transcript": "x" * 120})
    decisions = result.update.get("supervisor_decisions")
    assert decisions and decisions[0]["goto"] == "requirements_extractor"
    assert "reason" in decisions[0]
