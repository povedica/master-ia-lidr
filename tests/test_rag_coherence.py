"""Unit tests for post-generation coherence verification (feature-058)."""

from __future__ import annotations

from app.schemas.coherence_report import CoherenceLineStatus
from app.schemas.rag_estimation_result import (
    RagEstimationLineItem,
    RagEstimationResult,
    SourceReference,
)
from app.services.rag_coherence import check_coherence


def _result(
    *line_items: RagEstimationLineItem,
    total_hours: float | None = None,
    insufficient_context: bool = False,
) -> RagEstimationResult:
    items = list(line_items)
    computed_total = sum(item.hours for item in items)
    return RagEstimationResult(
        summary="Test estimate summary for coherence verification checks.",
        line_items=items,
        total_hours=computed_total if total_hours is None else total_hours,
        insufficient_context=insufficient_context,
    )


def _grounded_line(
    component: str,
    *,
    hours: float = 10.0,
    rationale: str = "Grounded rationale from budget chunk.",
) -> RagEstimationLineItem:
    return RagEstimationLineItem(
        component=component,
        hours=hours,
        rationale=rationale,
        grounded=True,
        sources=[
            SourceReference(
                chunk_id=42,
                document_id=7,
                evidence="OAuth2 login integration scope",
            )
        ],
    )


def test_coherent_estimate_has_no_violations() -> None:
    estimate = _result(_grounded_line("authentication", hours=12.0))

    report = check_coherence(estimate, request_id="req_ok")

    assert report.has_violations is False
    assert report.counts[CoherenceLineStatus.COHERENT_OK] == 1
    assert report.lines[0].status == CoherenceLineStatus.COHERENT_OK


def test_mismatched_total_hours_flags_violation() -> None:
    line = _grounded_line("authentication", hours=12.0)
    estimate = RagEstimationResult.model_construct(
        summary="Test estimate summary for coherence verification checks.",
        line_items=[line],
        total_hours=20.0,
        insufficient_context=False,
    )

    report = check_coherence(estimate, request_id="req_total")

    assert report.has_violations is True
    assert report.counts[CoherenceLineStatus.TOTAL_HOURS_MISMATCH] == 1


def test_duplicate_components_case_insensitive() -> None:
    estimate = _result(
        _grounded_line("Authentication", hours=5.0),
        _grounded_line("authentication", hours=3.0),
    )

    report = check_coherence(estimate, request_id="req_dup")

    assert report.has_violations is True
    assert report.counts[CoherenceLineStatus.DUPLICATE_COMPONENT] == 1
    assert report.lines[1].status == CoherenceLineStatus.DUPLICATE_COMPONENT


def test_insufficient_context_with_line_items_violates() -> None:
    estimate = _result(
        RagEstimationLineItem(
            component="analytics",
            hours=0.0,
            rationale="Should not appear when context is insufficient.",
            grounded=False,
            sources=[],
        ),
        insufficient_context=True,
    )

    report = check_coherence(estimate, request_id="req_insufficient")

    assert report.has_violations is True
    assert report.counts[CoherenceLineStatus.INSUFFICIENT_CONTEXT_VIOLATION] >= 1


def test_grounded_zero_hours_with_rationale_violates() -> None:
    estimate = _result(_grounded_line("authentication", hours=0.0))

    report = check_coherence(estimate, request_id="req_zero")

    assert report.has_violations is True
    assert report.lines[0].status == CoherenceLineStatus.ZERO_HOURS_GROUNDED


def test_disabled_returns_noop_report() -> None:
    line = _grounded_line("authentication", hours=12.0)
    estimate = RagEstimationResult.model_construct(
        summary="Test estimate summary for coherence verification checks.",
        line_items=[line],
        total_hours=99.0,
        insufficient_context=False,
    )

    report = check_coherence(estimate, request_id="req_disabled", enabled=False)

    assert report.has_violations is False
    assert report.lines == []
