"""Tests for cross-encoder reranker (feature-050)."""

from __future__ import annotations

import pytest

from app.embedding_pipeline.rerank import CrossEncoderReranker, RerankCandidate
from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry


def _entry(*, rank: int, chunk_id: int, score: float) -> BranchResultEntry:
    return BranchResultEntry(
        rank=rank,
        chunk_id=chunk_id,
        document_id=chunk_id + 1000,
        score=score,
    )


@pytest.mark.asyncio
async def test_cross_encoder_reranker_orders_by_fake_scorer_descending() -> None:
    def predict(pairs):
        del pairs
        return [0.2, 0.9, 0.5]

    reranker = CrossEncoderReranker("fake-model", predict=predict)
    candidates = [
        RerankCandidate(entry=_entry(rank=1, chunk_id=101, score=0.8), content="a"),
        RerankCandidate(entry=_entry(rank=2, chunk_id=102, score=0.7), content="b"),
        RerankCandidate(entry=_entry(rank=3, chunk_id=103, score=0.6), content="c"),
    ]

    reranked = await reranker.rerank("query", candidates)

    assert reranker.is_noop is False
    assert [item.candidate.entry.chunk_id for item in reranked] == [102, 103, 101]
    assert [item.rerank_rank for item in reranked] == [1, 2, 3]
