"""Tests for hybrid retrieval fusion primitives."""

from __future__ import annotations

import pytest

from app.embedding_pipeline.fusion import (
    build_ranking_diff,
    build_explanation,
    reciprocal_rank_fusion,
    weighted_fusion,
)
from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry


def _entry(*, rank: int, chunk_id: int, score: float) -> BranchResultEntry:
    return BranchResultEntry(
        rank=rank,
        chunk_id=chunk_id,
        document_id=chunk_id + 1000,
        score=score,
    )


def _vector_entry(
    *,
    rank: int,
    chunk_id: int,
    score: float,
    distance: float,
) -> BranchResultEntry:
    return BranchResultEntry(
        rank=rank,
        chunk_id=chunk_id,
        document_id=chunk_id + 1000,
        score=score,
        distance=distance,
    )


def _lexical_entry(
    *,
    rank: int,
    chunk_id: int,
    score: float,
    matched_terms: list[str],
) -> BranchResultEntry:
    return BranchResultEntry(
        rank=rank,
        chunk_id=chunk_id,
        document_id=chunk_id + 1000,
        score=score,
        matched_terms=matched_terms,
    )


def test_reciprocal_rank_fusion_scores_weights_and_tie_breaks() -> None:
    branch_rankings = {
        "vector": [
            _entry(rank=1, chunk_id=101, score=0.9),
            _entry(rank=2, chunk_id=102, score=0.8),
            _entry(rank=3, chunk_id=103, score=0.7),
        ],
        "lexical": [
            _entry(rank=1, chunk_id=103, score=0.95),
            _entry(rank=2, chunk_id=101, score=0.6),
            _entry(rank=3, chunk_id=102, score=0.5),
        ],
    }

    fused = reciprocal_rank_fusion(
        branch_rankings,
        k=60,
        weights={"vector": 1.0, "lexical": 2.0},
    )

    assert [entry.chunk_id for entry in fused] == [103, 101, 102]
    assert [entry.rank for entry in fused] == [1, 2, 3]
    assert fused[0].score == pytest.approx((1.0 / 63.0) + (2.0 / 61.0))

    tied = reciprocal_rank_fusion(
        {
            "vector": [_entry(rank=1, chunk_id=202, score=0.7)],
            "lexical": [_entry(rank=1, chunk_id=201, score=0.7)],
        },
        k=60,
    )

    assert [entry.chunk_id for entry in tied] == [201, 202]


def test_weighted_fusion_normalizes_weights_and_orders_by_weighted_score() -> None:
    branch_rankings = {
        "vector": [
            _entry(rank=1, chunk_id=101, score=0.4),
            _entry(rank=2, chunk_id=102, score=0.9),
        ],
        "lexical": [
            _entry(rank=1, chunk_id=101, score=1.0),
            _entry(rank=2, chunk_id=103, score=0.8),
        ],
    }

    fused = weighted_fusion(
        branch_rankings,
        weights={"vector": 1.0, "lexical": 3.0},
    )

    assert [entry.chunk_id for entry in fused] == [101, 103, 102]
    assert [entry.rank for entry in fused] == [1, 2, 3]
    assert fused[0].score == pytest.approx((0.25 * 0.4) + (0.75 * 1.0))
    assert fused[1].score == pytest.approx(0.75 * 0.8)
    assert fused[2].score == pytest.approx(0.25 * 0.9)


def test_build_ranking_diff_groups_consensus_rescues_and_movers() -> None:
    vector = [
        _entry(rank=1, chunk_id=101, score=0.9),
        _entry(rank=2, chunk_id=102, score=0.8),
        _entry(rank=5, chunk_id=104, score=0.5),
    ]
    lexical = [
        _entry(rank=1, chunk_id=101, score=1.0),
        _entry(rank=2, chunk_id=103, score=0.9),
        _entry(rank=6, chunk_id=104, score=0.4),
    ]
    final = [
        _entry(rank=1, chunk_id=103, score=0.7),
        _entry(rank=2, chunk_id=101, score=0.6),
        _entry(rank=3, chunk_id=104, score=0.5),
    ]

    diff = build_ranking_diff(
        {"vector": vector, "lexical": lexical},
        final,
        threshold_drops=[102],
        big_mover_threshold=2,
        rescue_rank_threshold=3,
    )

    assert [entry.chunk_id for entry in diff.common] == [101, 104]
    assert [entry.chunk_id for entry in diff.vector_only] == [102]
    assert [entry.chunk_id for entry in diff.lexical_only] == [103]
    assert [entry.chunk_id for entry in diff.hybrid_rescued] == [103]
    assert [(mover.chunk_id, mover.from_rank, mover.to_rank, mover.delta) for mover in diff.big_movers] == [
        (104, 5, 3, 2)
    ]
    assert [entry.chunk_id for entry in diff.dropped_by_threshold] == [102]
    assert diff.dropped_by_rerank == []


def test_build_explanation_uses_controlled_signals() -> None:
    branches = {
        "vector": [
            _vector_entry(rank=1, chunk_id=101, score=0.8, distance=0.2),
            _vector_entry(rank=2, chunk_id=102, score=0.3, distance=0.7),
        ],
        "lexical": [
            _lexical_entry(rank=1, chunk_id=101, score=1.0, matched_terms=["oauth2"]),
            _lexical_entry(rank=2, chunk_id=103, score=0.9, matched_terms=["jwt"]),
        ],
    }
    final = [
        _entry(rank=1, chunk_id=103, score=0.7),
        _entry(rank=2, chunk_id=101, score=0.6),
        _entry(rank=3, chunk_id=102, score=0.5),
    ]
    diff = build_ranking_diff(
        branches,
        final,
        threshold_drops=[102],
        big_mover_threshold=2,
        rescue_rank_threshold=2,
    )

    consensus = build_explanation(final[1], branches=branches, diff=diff, threshold=0.5)
    rescued = build_explanation(final[0], branches=branches, diff=diff, threshold=0.5)
    weak = build_explanation(final[2], branches=branches, diff=diff, threshold=0.5)

    assert consensus.signals == [
        "semantic_strong",
        "lexical_exact_match",
        "branch_consensus",
    ]
    assert "consensus" in consensus.summary
    assert rescued.signals == ["lexical_exact_match", "hybrid_rescued"]
    assert "rescued" in rescued.summary
    assert weak.signals == ["semantic_weak", "below_threshold"]
