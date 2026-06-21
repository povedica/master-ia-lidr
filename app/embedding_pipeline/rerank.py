"""Rerank contracts for retrieval debug diagnostics."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
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


PairScorer = Callable[[Sequence[tuple[str, str]]], list[float]]


class CrossEncoderReranker:
    """Cross-encoder reranker backed by sentence-transformers (lazy-loaded)."""

    is_noop = False

    def __init__(
        self,
        model_id: str,
        *,
        predict: PairScorer | None = None,
    ) -> None:
        self._model_id = model_id
        self._predict = predict
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_id)
        return self._model

    def _score_pairs(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        if self._predict is not None:
            return list(self._predict(pairs))
        model = self._load_model()
        raw_scores = model.predict(list(pairs))
        return [float(score) for score in raw_scores]

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankedItem]:
        if not candidates:
            return []
        pairs = [(query, candidate.content) for candidate in candidates]
        scores = await asyncio.to_thread(self._score_pairs, pairs)
        ranked = sorted(
            zip(candidates, scores, strict=True),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            RerankedItem(
                candidate=candidate,
                rerank_rank=rank,
                rerank_score=score,
            )
            for rank, (candidate, score) in enumerate(ranked, start=1)
        ]


def build_reranker(settings: Any) -> Reranker:
    """Resolve the configured reranker from application settings."""

    if not settings.retrieval_rerank_enabled:
        return NoOpReranker()
    model_id = settings.retrieval_rerank_model.strip()
    if not model_id:
        return NoOpReranker()
    return CrossEncoderReranker(model_id)
