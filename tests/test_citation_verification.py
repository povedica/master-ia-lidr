"""Unit tests for post-generation citation verification (FR-07)."""

from __future__ import annotations

from app.schemas.citation_report import CitationLineStatus
from app.schemas.rag_estimation_result import (
    RagEstimationLineItem,
    RagEstimationResult,
    SourceReference,
)
from app.services.citation_verification import verify_citations


def _result(*line_items: RagEstimationLineItem) -> RagEstimationResult:
    return RagEstimationResult(
        summary="Test estimate summary for citation verification checks.",
        line_items=list(line_items),
        total_hours=sum(item.hours for item in line_items),
        insufficient_context=False,
    )


def test_grounded_ok_when_all_chunk_ids_in_context() -> None:
    estimate = _result(
        RagEstimationLineItem(
            component="auth",
            hours=10.0,
            rationale="OAuth2 scope from budget chunk.",
            grounded=True,
            sources=[
                SourceReference(
                    chunk_id=42,
                    document_id=7,
                    evidence="OAuth2 login integration",
                )
            ],
        )
    )

    report = verify_citations(estimate, retrieved_chunk_ids={42}, request_id="req_1")

    assert report.lines[0].status == CitationLineStatus.GROUNDED_OK
    assert report.has_dangling is False
    assert report.counts[CitationLineStatus.GROUNDED_OK] == 1


def test_dangling_citation_for_unknown_chunk_id() -> None:
    estimate = _result(
        RagEstimationLineItem(
            component="auth",
            hours=10.0,
            rationale="Cites chunk not in retrieval set.",
            grounded=True,
            sources=[
                SourceReference(
                    chunk_id=999,
                    document_id=7,
                    evidence="Fabricated chunk reference",
                )
            ],
        )
    )

    report = verify_citations(estimate, retrieved_chunk_ids={42}, request_id="req_2")

    assert report.lines[0].status == CitationLineStatus.DANGLING_CITATION
    assert report.lines[0].invalid_chunk_ids == [999]
    assert report.has_dangling is True
    assert report.counts[CitationLineStatus.DANGLING_CITATION] == 1


def test_insufficient_data_line_classification() -> None:
    estimate = _result(
        RagEstimationLineItem(
            component="analytics",
            hours=0.0,
            rationale="No analytics evidence in retrieved context.",
            grounded=False,
            sources=[],
        )
    )

    report = verify_citations(estimate, retrieved_chunk_ids={42}, request_id="req_3")

    assert report.lines[0].status == CitationLineStatus.INSUFFICIENT_DATA
    assert report.counts[CitationLineStatus.INSUFFICIENT_DATA] == 1


def test_mixed_grounded_ok_and_dangling_lines() -> None:
    estimate = _result(
        RagEstimationLineItem(
            component="auth",
            hours=8.0,
            rationale="Valid chunk citation.",
            grounded=True,
            sources=[
                SourceReference(
                    chunk_id=42,
                    document_id=7,
                    evidence="OAuth2",
                )
            ],
        ),
        RagEstimationLineItem(
            component="wallet",
            hours=6.0,
            rationale="Invalid chunk citation.",
            grounded=True,
            sources=[
                SourceReference(
                    chunk_id=100,
                    document_id=7,
                    evidence="PSD2 wallet",
                )
            ],
        ),
    )

    report = verify_citations(estimate, retrieved_chunk_ids={42}, request_id="req_4")

    assert report.lines[0].status == CitationLineStatus.GROUNDED_OK
    assert report.lines[1].status == CitationLineStatus.DANGLING_CITATION
    assert report.has_dangling is True


def test_empty_estimate_produces_empty_report() -> None:
    estimate = RagEstimationResult(
        summary="Insufficient context; no line items were produced.",
        line_items=[],
        total_hours=0.0,
        insufficient_context=True,
    )

    report = verify_citations(estimate, retrieved_chunk_ids=set(), request_id="req_5")

    assert report.lines == []
    assert report.has_dangling is False
    assert report.counts[CitationLineStatus.GROUNDED_OK] == 0
