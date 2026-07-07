"""Unit tests for RAG hallucination gate pure logic (feature-060 step 1)."""

from __future__ import annotations

from app.schemas.hallucination_report import HallucinationLineGrade
from app.services.rag_hallucination_gate import gate_line, numeric_anchor

_INFLATED_HOURS_CHUNK = (
    "OAuth2 login integration scope — prior budget line: 8 hours "
    "for authentication module including SSO callbacks."
)


def test_numeric_anchor_extracts_hour_patterns() -> None:
    chunks = [
        "Authentication module: 8 hours for OAuth2 login flow.",
        "Stripe checkout integration budgeted at 12.5 hrs.",
        "No numeric budget reference in this chunk.",
        "Quick spike: 3h for webhook wiring.",
    ]

    anchors = numeric_anchor(chunks)

    assert anchors == [3.0, 8.0, 12.5]


def test_numeric_anchor_empty_when_no_hour_like_numbers() -> None:
    anchors = numeric_anchor(
        [
            "OAuth2 login integration scope without hour figures.",
            "Discuss SSO callbacks and token refresh only.",
        ]
    )

    assert anchors == []


def test_gate_line_grounded_within_tolerance_of_anchor_max() -> None:
    grade = gate_line(line_hours=9.0, anchor_hours=[8.0], tolerance=0.25)

    assert grade == HallucinationLineGrade.GROUNDED


def test_gate_line_degraded_when_hours_far_above_anchor_max() -> None:
    grade = gate_line(line_hours=80.0, anchor_hours=[8.0], tolerance=0.25)

    assert grade == HallucinationLineGrade.DEGRADED


def test_gate_line_insufficient_when_no_anchors() -> None:
    grade = gate_line(line_hours=12.0, anchor_hours=[])

    assert grade == HallucinationLineGrade.INSUFFICIENT


def test_inflated_hours_fixture_marks_line_degraded() -> None:
    """AC-11 from feature-053: canned chunk vs inflated line hours."""

    anchors = numeric_anchor([_INFLATED_HOURS_CHUNK])

    assert anchors == [8.0]
    assert gate_line(line_hours=80.0, anchor_hours=anchors) == HallucinationLineGrade.DEGRADED
