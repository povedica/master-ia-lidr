"""Rerank contracts for retrieval debug diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry


@dataclass(frozen=True)
class RerankCandidate:
    """One ordered candidate sent to a reranker."""

    entry: BranchResultEntry
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RerankedItem:
    """One candidate returned by a reranker with rerank-specific evidence."""

    candidate: RerankCandidate
    rerank_rank: int
    rerank_score: float | None = None


class Reranker(Protocol):
    """Stable interface for future retrieval rerankers."""

    is_noop: bool

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankedItem]:
        """Return candidates in reranked order."""


class NoOpReranker:
    """Transparent placeholder reranker that preserves input order."""

    is_noop = True

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankedItem]:
        del query
        return [
            RerankedItem(candidate=candidate, rerank_rank=rank)
            for rank, candidate in enumerate(candidates, start=1)
        ]
