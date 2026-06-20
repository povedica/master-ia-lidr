"""Tests for vector branch adaptation in retrieval debug (feature-042)."""

from __future__ import annotations

import pytest

from app.embedding_pipeline.retrieval_debug import build_vector_branch_entries
from app.embedding_pipeline.retrieval_debug import build_vector_explanation
from app.embedding_pipeline.retrieval_debug import filter_vector_branch_entries
from app.embedding_pipeline.schemas import SearchResult


def _search_result(
    *,
    chunk_id: int,
    document_id: int = 12,
    distance: float,
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        document_id=document_id,
        chunk_type="budget_component",
        content="Backend OAuth implementation",
        distance=distance,
        metadata={"component_id": "AUTH-001"},
    )


def test_build_vector_branch_entries_preserves_order_and_adds_rank() -> None:
    results = [
        _search_result(chunk_id=101, distance=0.12),
        _search_result(chunk_id=102, distance=0.31),
    ]

    entries = build_vector_branch_entries(results)

    assert [entry.rank for entry in entries] == [1, 2]
    assert [entry.chunk_id for entry in entries] == [101, 102]
    assert entries[0].distance == pytest.approx(0.12)
    assert entries[1].score == pytest.approx(0.69)


def test_build_vector_branch_entries_clamps_normalized_score() -> None:
    results = [
        _search_result(chunk_id=101, distance=0.0),
        _search_result(chunk_id=102, distance=1.4),
    ]

    entries = build_vector_branch_entries(results)

    assert entries[0].score == pytest.approx(1.0)
    assert entries[1].score == pytest.approx(0.0)


def test_build_vector_explanation_marks_strong_and_weak_semantic_signals() -> None:
    strong, weak = build_vector_branch_entries(
        [
            _search_result(chunk_id=101, distance=0.32),
            _search_result(chunk_id=102, distance=0.65),
        ]
    )

    strong_explanation = build_vector_explanation(strong)
    weak_explanation = build_vector_explanation(weak)

    assert strong_explanation.signals == ["semantic_strong"]
    assert "strong semantic match" in strong_explanation.summary
    assert weak_explanation.signals == ["semantic_weak"]
    assert "weaker semantic match" in weak_explanation.summary


def test_build_vector_explanation_marks_below_threshold() -> None:
    (entry,) = build_vector_branch_entries([_search_result(chunk_id=101, distance=0.55)])

    explanation = build_vector_explanation(entry, threshold=0.6)

    assert explanation.signals == ["semantic_weak", "below_threshold"]
    assert "below the configured threshold" in explanation.summary


def test_filter_vector_branch_entries_drops_scores_below_threshold() -> None:
    entries = build_vector_branch_entries(
        [
            _search_result(chunk_id=101, distance=0.2),
            _search_result(chunk_id=102, distance=0.55),
        ]
    )

    filtered = filter_vector_branch_entries(entries, threshold=0.6)

    assert [entry.chunk_id for entry in filtered] == [101]
