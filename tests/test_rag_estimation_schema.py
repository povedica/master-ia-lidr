"""Unit tests for RAG estimation domain schema (FR-01–03)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.rag_estimation_result import (
    RagEstimationLineItem,
    RagEstimationResult,
    SourceReference,
)


def _source(chunk_id: int = 42, document_id: int = 7) -> SourceReference:
    return SourceReference(
        chunk_id=chunk_id,
        document_id=document_id,
        budget_id="BUD-2024-014",
        evidence="Stripe OAuth2 integration scope",
    )


def test_grounded_true_requires_non_empty_sources() -> None:
    with pytest.raises(ValidationError, match="sources"):
        RagEstimationLineItem(
            component="authentication",
            hours=8.0,
            rationale="OAuth2 flow based on retrieved budget evidence.",
            grounded=True,
            sources=[],
        )


def test_grounded_false_rejects_non_zero_hours() -> None:
    with pytest.raises(ValidationError):
        RagEstimationLineItem(
            component="payments",
            hours=5.0,
            rationale="No supporting chunk for PSD2 wallet scope in context.",
            grounded=False,
            sources=[],
        )


def test_grounded_false_rejects_non_empty_sources() -> None:
    with pytest.raises(ValidationError):
        RagEstimationLineItem(
            component="payments",
            hours=0.0,
            rationale="No supporting chunk for PSD2 wallet scope in context.",
            grounded=False,
            sources=[_source()],
        )


def test_source_reference_rejects_invalid_chunk_id() -> None:
    with pytest.raises(ValidationError):
        SourceReference(
            chunk_id=0,
            document_id=7,
            evidence="valid evidence text",
        )


def test_source_reference_rejects_whitespace_evidence() -> None:
    with pytest.raises(ValidationError):
        SourceReference(
            chunk_id=42,
            document_id=7,
            evidence="   ",
        )


def test_total_hours_recomputed_from_line_items() -> None:
    result = RagEstimationResult(
        summary="Grounded estimate for e-commerce platform with Stripe and OAuth2.",
        line_items=[
            RagEstimationLineItem(
                component="authentication",
                hours=12.0,
                rationale="OAuth2 login and token refresh from budget chunk.",
                grounded=True,
                sources=[_source()],
            ),
            RagEstimationLineItem(
                component="payments",
                hours=8.0,
                rationale="Stripe checkout integration from budget chunk.",
                grounded=True,
                sources=[_source(chunk_id=43, document_id=7)],
            ),
        ],
        total_hours=999.0,
        insufficient_context=False,
    )
    assert result.total_hours == 20.0
    assert result.schema_version == "rag-1"


def test_valid_grounded_and_insufficient_line_items() -> None:
    result = RagEstimationResult(
        summary="Partial estimate with one grounded line and one insufficiency.",
        line_items=[
            RagEstimationLineItem(
                component="catalog",
                hours=6.0,
                rationale="Product catalog module described in retrieved chunk.",
                grounded=True,
                sources=[_source()],
            ),
            RagEstimationLineItem(
                component="analytics",
                hours=0.0,
                rationale="No retrieved chunk mentions analytics dashboards.",
                grounded=False,
                sources=[],
            ),
        ],
        total_hours=0.0,
        insufficient_context=False,
    )
    assert result.total_hours == 6.0
