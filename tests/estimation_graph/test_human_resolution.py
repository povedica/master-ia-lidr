"""Typed human-resolution models for graph resume (feature-067)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.graph_estimation import (
    AdjustResolution,
    ApproveResolution,
    HumanResolution,
    RejectResolution,
    parse_human_resolution,
)


def test_approve_resolution_parses() -> None:
    resolved = parse_human_resolution(
        {"action": "approve", "comment": "Historical analogy is acceptable."}
    )
    assert isinstance(resolved, ApproveResolution)
    assert resolved.action == "approve"
    assert resolved.comment == "Historical analogy is acceptable."


def test_adjust_resolution_requires_adjusted_estimate() -> None:
    resolved = parse_human_resolution(
        {
            "action": "adjust",
            "adjusted_estimate": {
                "components": [{"name": "API", "estimated_hours": 120.0}],
                "total_hours": 420.0,
            },
            "comment": "Adjusted integration effort.",
        }
    )
    assert isinstance(resolved, AdjustResolution)
    assert resolved.adjusted_estimate["total_hours"] == 420.0


def test_adjust_resolution_rejects_missing_estimate() -> None:
    with pytest.raises(ValidationError):
        parse_human_resolution({"action": "adjust", "comment": "no estimate"})


def test_reject_resolution_parses() -> None:
    resolved = parse_human_resolution(
        {
            "action": "reject",
            "comment": "Transcript is insufficient; request a new discovery call.",
        }
    )
    assert isinstance(resolved, RejectResolution)
    assert resolved.action == "reject"


def test_unknown_action_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_human_resolution({"action": "defer"})


def test_human_resolution_union_accepts_all_variants() -> None:
    for payload in (
        {"action": "approve"},
        {
            "action": "adjust",
            "adjusted_estimate": {"components": [], "total_hours": 10.0},
        },
        {"action": "reject"},
    ):
        resolved = parse_human_resolution(payload)
        assert isinstance(resolved, (ApproveResolution, AdjustResolution, RejectResolution))
        # Keep the alias imported so the public contract stays wired.
        assert HumanResolution is not None
