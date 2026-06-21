"""Tests for hybrid retrieval fusion primitives."""

from __future__ import annotations

import pytest

from app.embedding_pipeline.fusion import (
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
