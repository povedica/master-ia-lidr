"""Tests for retrieval rerank contracts."""

from __future__ import annotations

import pytest

from app.embedding_pipeline.rerank import NoOpReranker, RerankCandidate
from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry


def _entry(*, rank: int, chunk_id: int, score: float) -> BranchResultEntry:
    return BranchResultEntry(
        rank=rank,
        chunk_id=chunk_id,
        document_id=chunk_id + 1000,
        score=score,
    )


@pytest.mark.asyncio
async def test_noop_reranker_preserves_input_order_and_sets_ranks() -> None:
    candidates = [
        RerankCandidate(entry=_entry(rank=1, chunk_id=101, score=0.8), content="OAuth backend"),
        RerankCandidate(entry=_entry(rank=2, chunk_id=102, score=0.7), content="JWT frontend"),
    ]
    reranker = NoOpReranker()

    reranked = await reranker.rerank("OAuth", candidates)

    assert reranker.is_noop is True
    assert [item.candidate.entry.chunk_id for item in reranked] == [101, 102]
    assert [item.rerank_rank for item in reranked] == [1, 2]
    assert [item.rerank_score for item in reranked] == [None, None]
