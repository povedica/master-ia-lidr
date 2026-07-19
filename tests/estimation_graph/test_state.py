"""Reducer semantics for EstimationState (feature-067)."""

from __future__ import annotations

import operator
import typing

from langgraph.channels import BinaryOperatorAggregate
from langgraph.graph import END, START, StateGraph

from app.services.estimation_graph.state import (
    EstimationState,
    merge_agent_contributions,
    merge_budget_matches,
    merge_completed_workers,
)


def _channels():
    builder = StateGraph(EstimationState)
    builder.add_node("noop", lambda state: {})
    builder.add_edge(START, "noop")
    builder.add_edge("noop", END)
    return builder.compile().channels


def test_budget_matches_use_keyed_reducer_not_operator_add() -> None:
    hints = typing.get_type_hints(EstimationState, include_extras=True)
    metadata = getattr(hints["budget_matches"], "__metadata__", ())
    assert merge_budget_matches in metadata
    assert operator.add not in metadata


def test_agent_contributions_and_errors_use_operator_add() -> None:
    hints = typing.get_type_hints(EstimationState, include_extras=True)
    assert operator.add in getattr(hints["agent_contributions"], "__metadata__", ())
    assert operator.add in getattr(hints["errors"], "__metadata__", ())


def test_completed_workers_uses_set_union_reducer() -> None:
    hints = typing.get_type_hints(EstimationState, include_extras=True)
    metadata = getattr(hints["completed_workers"], "__metadata__", ())
    assert merge_completed_workers in metadata


def test_accumulator_fields_compile_to_reducer_channels() -> None:
    channels = _channels()
    assert isinstance(channels["budget_matches"], BinaryOperatorAggregate)
    assert isinstance(channels["agent_contributions"], BinaryOperatorAggregate)
    assert isinstance(channels["completed_workers"], BinaryOperatorAggregate)
    assert isinstance(channels["errors"], BinaryOperatorAggregate)
    assert not isinstance(channels["requirements"], BinaryOperatorAggregate)


def test_merge_budget_matches_dedupes_by_requirement_and_reference() -> None:
    existing = [
        {
            "requirement_id": "req-1",
            "reference_budget_id": "b1",
            "amount": 80.0,
            "distance": 0.1,
            "component": "API",
        },
        {
            "requirement_id": "req-2",
            "reference_budget_id": "b2",
            "amount": 40.0,
            "distance": 0.2,
            "component": "UI",
        },
    ]
    new = [
        {
            "requirement_id": "req-1",
            "reference_budget_id": "b1",
            "amount": 96.0,
            "distance": 0.05,
            "component": "API",
        }
    ]
    merged = merge_budget_matches(existing, new)
    by_key = {
        (row["requirement_id"], row["reference_budget_id"]): row["amount"] for row in merged
    }
    assert by_key == {("req-1", "b1"): 96.0, ("req-2", "b2"): 40.0}
    assert len(merged) == 2


def test_merge_budget_matches_keeps_no_match_markers() -> None:
    """A search with no precedent still records an attempted outcome."""
    new = [
        {
            "requirement_id": "req-x",
            "reference_budget_id": None,
            "amount": 0.0,
            "distance": 1.0,
            "component": "Unknown domain",
            "no_match": True,
        }
    ]
    merged = merge_budget_matches([], new)
    assert len(merged) == 1
    assert merged[0]["no_match"] is True
    # Re-entry with the same no-match marker must not duplicate.
    again = merge_budget_matches(merged, new)
    assert len(again) == 1


def test_merge_budget_matches_handles_empty_sides() -> None:
    row = {
        "requirement_id": "r",
        "reference_budget_id": "b",
        "amount": 8.0,
        "distance": 0.3,
        "component": "X",
    }
    assert merge_budget_matches(None, [row]) == [row]
    assert merge_budget_matches([row], None) == [row]


def test_merge_agent_contributions_appends() -> None:
    assert merge_agent_contributions(
        [{"worker": "requirements_extractor"}],
        [{"worker": "budget_searcher"}],
    ) == [
        {"worker": "requirements_extractor"},
        {"worker": "budget_searcher"},
    ]


def test_merge_completed_workers_unions_without_duplicates() -> None:
    merged = merge_completed_workers(
        ["requirements_extractor"],
        ["requirements_extractor", "budget_searcher"],
    )
    assert set(merged) == {"requirements_extractor", "budget_searcher"}
    assert len(merged) == 2


def test_errors_reducer_appends_without_clobbering() -> None:
    channel = _channels()["errors"].copy()
    channel.update([["first issue"]])
    channel.update([["second issue"]])
    assert channel.get() == ["first issue", "second issue"]


def test_state_declares_supervisor_hitl_fields() -> None:
    hints = typing.get_type_hints(EstimationState, include_extras=True)
    for field in (
        "transcript",
        "estimation_id",
        "requirements",
        "budget_matches",
        "estimate",
        "validation",
        "confidence",
        "status",
        "completed_workers",
        "agent_contributions",
        "human_review",
        "human_resolution",
        "search_attempted",
        "last_route",
        "route_reason",
        "human_adjustment_validated",
        "errors",
    ):
        assert field in hints
