"""Production retrieval orchestration for modes A/B/C/D (feature-050)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.fusion import reciprocal_rank_fusion
from app.embedding_pipeline.lexical_search_repository import (
    LexicalSearchRepository,
    LexicalSearchResult,
)
from app.embedding_pipeline.rerank import NoOpReranker, RerankCandidate, Reranker, RerankedItem
from app.embedding_pipeline.retrieval_debug import (
    build_lexical_branch_entries,
    build_vector_branch_entries,
)
from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry
from app.embedding_pipeline.retrieval_schemas import (
    RetrievalAppliedConfig,
    RetrievalFusionConfig,
    RetrievalRerankConfig,
    RetrievalResponse,
    RetrievalResultRow,
    RetrievalTimingsMs,
)
from app.embedding_pipeline.schemas import SearchResult
from app.embedding_pipeline.search_repository import SemanticSearchRepository

logger = logging.getLogger(__name__)

_NOOP_RERANK_WARNING = (
    "rerank requested but no reranker configured; rerank is a no-op placeholder"
)
_RERANK_DISABLED_WARNING = "rerank disabled by RETRIEVAL_RERANK_ENABLED=false"


class RetrievalMode(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass(frozen=True)
class RetrievalPlan:
    branches: tuple[str, ...]
    fusion_enabled: bool
    rerank_enabled: bool


def resolve_mode(mode: RetrievalMode) -> RetrievalPlan:
    mapping = {
        RetrievalMode.A: RetrievalPlan(("vector",), fusion_enabled=False, rerank_enabled=False),
        RetrievalMode.B: RetrievalPlan(
            ("vector", "lexical"),
            fusion_enabled=True,
            rerank_enabled=False,
        ),
        RetrievalMode.C: RetrievalPlan(("vector",), fusion_enabled=False, rerank_enabled=True),
        RetrievalMode.D: RetrievalPlan(
            ("vector", "lexical"),
            fusion_enabled=True,
            rerank_enabled=True,
        ),
    }
    return mapping[mode]


def parse_retrieval_mode(value: str) -> RetrievalMode:
    normalized = value.strip().upper()
    try:
        return RetrievalMode(normalized)
    except ValueError as exc:
        raise ValueError(f"Unsupported retrieval mode: {value}") from exc


def _budget_id(metadata: dict[str, Any]) -> str | None:
    raw = metadata.get("budget_id")
    return str(raw) if raw is not None else None


def _entry_maps(
    vector_entries: list[BranchResultEntry] | None,
    lexical_entries: list[BranchResultEntry] | None,
) -> tuple[dict[int, BranchResultEntry], dict[int, BranchResultEntry]]:
    vector_by_chunk = {entry.chunk_id: entry for entry in vector_entries or []}
    lexical_by_chunk = {entry.chunk_id: entry for entry in lexical_entries or []}
    return vector_by_chunk, lexical_by_chunk


def _content_and_metadata(
    chunk_id: int,
    *,
    vector_results: list[SearchResult],
    lexical_results: list[LexicalSearchResult],
) -> tuple[str, dict[str, Any], str | None]:
    for result in vector_results:
        if result.chunk_id == chunk_id:
            return result.content, dict(result.metadata), _budget_id(result.metadata)
    for result in lexical_results:
        if result.chunk_id == chunk_id:
            return result.content, dict(result.metadata), _budget_id(result.metadata)
    return "", {}, None


def _source_strategies(
    chunk_id: int,
    *,
    vector_by_chunk: dict[int, BranchResultEntry],
    lexical_by_chunk: dict[int, BranchResultEntry],
    reranked: bool,
) -> list[str]:
    strategies: list[str] = []
    if chunk_id in vector_by_chunk:
        strategies.append("vector")
    if chunk_id in lexical_by_chunk:
        strategies.append("lexical")
    if reranked:
        strategies.append("rerank")
    return strategies


def _normalize_rerank_scores(items: list[RerankedItem]) -> list[RerankedItem]:
    raw_scores = [item.rerank_score for item in items if item.rerank_score is not None]
    if not raw_scores:
        return items
    min_score = min(raw_scores)
    max_score = max(raw_scores)
    if max_score == min_score:
        return [
            RerankedItem(
                candidate=item.candidate,
                rerank_rank=item.rerank_rank,
                rerank_score=1.0,
            )
            for item in items
        ]
    normalized: list[RerankedItem] = []
    for item in items:
        if item.rerank_score is None:
            normalized.append(item)
            continue
        score = (item.rerank_score - min_score) / (max_score - min_score)
        normalized.append(
            RerankedItem(
                candidate=item.candidate,
                rerank_rank=item.rerank_rank,
                rerank_score=max(0.0, min(1.0, score)),
            )
        )
    return normalized


class RetrievalService:
    """Orchestrate vector, lexical, fusion, and rerank for production retrieval."""

    async def retrieve(
        self,
        query: str,
        *,
        mode: RetrievalMode,
        recall_k: int,
        top_k_final: int,
        session: AsyncSession,
        embedder: OpenAIEmbedder,
        reranker: Reranker,
        settings: Settings,
        vector_repository: SemanticSearchRepository | None = None,
        lexical_repository: LexicalSearchRepository | None = None,
    ) -> RetrievalResponse:
        total_started = time.perf_counter()
        plan = resolve_mode(mode)
        warnings: list[str] = []
        effective_plan = plan
        effective_mode = mode

        rerank_requested = plan.rerank_enabled
        rerank_active = rerank_requested and settings.retrieval_rerank_enabled
        if rerank_requested and not settings.retrieval_rerank_enabled:
            warnings.append(_RERANK_DISABLED_WARNING)
            effective_plan = _degraded_plan_without_rerank(plan)
            effective_mode = _mode_without_rerank(mode)
        elif rerank_requested and reranker.is_noop:
            warnings.append(_NOOP_RERANK_WARNING)
            effective_plan = _degraded_plan_without_rerank(plan)
            effective_mode = _mode_without_rerank(mode)

        vector_repo = vector_repository or SemanticSearchRepository()
        lexical_repo = lexical_repository or LexicalSearchRepository(
            text_search_config=settings.retrieval_lexical_text_search_config,
        )

        vector_results: list[SearchResult] = []
        lexical_results: list[LexicalSearchResult] = []
        vector_entries: list[BranchResultEntry] | None = None
        lexical_entries: list[BranchResultEntry] | None = None
        vector_ms = 0
        lexical_ms = 0
        fusion_ms = 0
        rerank_ms = 0

        async def run_vector_branch() -> tuple[list[SearchResult], list[BranchResultEntry], int]:
            started = time.perf_counter()
            query_vector = await embedder.embed_one(query)
            results = await vector_repo.search_chunks(
                session,
                query_vector=query_vector,
                k=recall_k,
            )
            return (
                results,
                build_vector_branch_entries(results),
                int((time.perf_counter() - started) * 1000),
            )

        async def run_lexical_branch() -> tuple[list[LexicalSearchResult], list[BranchResultEntry], int]:
            started = time.perf_counter()
            results = await lexical_repo.search_chunks(
                session,
                query=query,
                top_k=recall_k,
            )
            return (
                results,
                build_lexical_branch_entries(results),
                int((time.perf_counter() - started) * 1000),
            )

        branch_tasks: list[tuple[str, Any]] = []
        if "vector" in effective_plan.branches:
            branch_tasks.append(("vector", run_vector_branch()))
        if "lexical" in effective_plan.branches:
            branch_tasks.append(("lexical", run_lexical_branch()))

        if branch_tasks:
            branch_outputs = await asyncio.gather(
                *(task for _, task in branch_tasks),
                return_exceptions=True,
            )
            for (branch_name, _), output in zip(branch_tasks, branch_outputs, strict=True):
                if isinstance(output, Exception):
                    warnings.append(f"{branch_name.title()} branch failed: {type(output).__name__}")
                    continue
                if branch_name == "vector":
                    vector_results, vector_entries, vector_ms = output
                if branch_name == "lexical":
                    lexical_results, lexical_entries, lexical_ms = output

        ordered_entries: list[BranchResultEntry] = []
        reranked = False

        if effective_plan.fusion_enabled and vector_entries is not None and lexical_entries is not None:
            fusion_started = time.perf_counter()
            ordered_entries = reciprocal_rank_fusion(
                {"vector": vector_entries, "lexical": lexical_entries},
                k=settings.retrieval_rrf_k,
            )[:recall_k]
            fusion_ms = int((time.perf_counter() - fusion_started) * 1000)
        elif vector_entries is not None:
            ordered_entries = vector_entries[:recall_k]
        elif lexical_entries is not None:
            ordered_entries = lexical_entries[:recall_k]

        rerank_score_by_chunk: dict[int, float] = {}
        if effective_plan.rerank_enabled and ordered_entries and rerank_active and not reranker.is_noop:
            rerank_started = time.perf_counter()
            candidates = []
            for entry in ordered_entries:
                content, metadata, _ = _content_and_metadata(
                    entry.chunk_id,
                    vector_results=vector_results,
                    lexical_results=lexical_results,
                )
                candidates.append(
                    RerankCandidate(entry=entry, content=content, metadata=metadata),
                )
            reranked_items = _normalize_rerank_scores(
                await reranker.rerank(query, candidates),
            )
            ordered_entries = [
                item.candidate.entry
                for item in sorted(reranked_items, key=lambda item: item.rerank_rank)
            ]
            rerank_score_by_chunk = {
                item.candidate.entry.chunk_id: item.rerank_score or 0.0
                for item in reranked_items
            }
            reranked = True
            rerank_ms = int((time.perf_counter() - rerank_started) * 1000)

        ordered_entries = ordered_entries[:top_k_final]
        vector_by_chunk, lexical_by_chunk = _entry_maps(vector_entries, lexical_entries)

        results: list[RetrievalResultRow] = []
        for position, entry in enumerate(ordered_entries, start=1):
            _, metadata, budget_id = _content_and_metadata(
                entry.chunk_id,
                vector_results=vector_results,
                lexical_results=lexical_results,
            )
            vector_entry = vector_by_chunk.get(entry.chunk_id)
            lexical_entry = lexical_by_chunk.get(entry.chunk_id)
            rerank_score = rerank_score_by_chunk.get(entry.chunk_id)
            fusion_score = entry.score if effective_plan.fusion_enabled else None
            final_score = (
                rerank_score
                if rerank_score is not None
                else fusion_score
                if fusion_score is not None
                else vector_entry.score
                if vector_entry is not None
                else lexical_entry.score
                if lexical_entry is not None
                else entry.score
            )
            results.append(
                RetrievalResultRow(
                    final_position=position,
                    chunk_id=entry.chunk_id,
                    document_id=entry.document_id,
                    budget_id=budget_id,
                    score=final_score or 0.0,
                    vector_score=vector_entry.score if vector_entry is not None else None,
                    lexical_score=lexical_entry.score if lexical_entry is not None else None,
                    fusion_score=fusion_score,
                    rerank_score=rerank_score,
                    matched_terms=list(lexical_entry.matched_terms) if lexical_entry else [],
                    source_strategies=_source_strategies(
                        entry.chunk_id,
                        vector_by_chunk=vector_by_chunk,
                        lexical_by_chunk=lexical_by_chunk,
                        reranked=reranked,
                    ),
                    metadata=metadata,
                )
            )

        total_ms = int((time.perf_counter() - total_started) * 1000)
        applied_config = RetrievalAppliedConfig(
            mode=effective_mode.value,
            branches=list(effective_plan.branches),
            fusion=(
                RetrievalFusionConfig(rrf_k=settings.retrieval_rrf_k)
                if effective_plan.fusion_enabled
                else None
            ),
            rerank=RetrievalRerankConfig(
                enabled=rerank_requested,
                model=settings.retrieval_rerank_model,
                is_noop=rerank_requested and (reranker.is_noop or not settings.retrieval_rerank_enabled),
            ),
            recall_k=recall_k,
            top_k_final=top_k_final,
            text_search_config=settings.retrieval_lexical_text_search_config,
        )
        logger.info(
            "retrieval_completed",
            extra={
                "mode": effective_mode.value,
                "vector_count": len(vector_entries or []),
                "lexical_count": len(lexical_entries or []),
                "fused_count": len(ordered_entries),
                "final_count": len(results),
                "timings_ms": {
                    "vector": vector_ms,
                    "lexical": lexical_ms,
                    "fusion": fusion_ms,
                    "rerank": rerank_ms,
                    "total": total_ms,
                },
                "rerank_is_noop": applied_config.rerank.is_noop,
            },
        )
        return RetrievalResponse(
            query=query,
            mode=effective_mode.value,
            applied_config=applied_config,
            timings_ms=RetrievalTimingsMs(
                vector=vector_ms,
                lexical=lexical_ms,
                fusion=fusion_ms,
                rerank=rerank_ms,
                total=total_ms,
            ),
            results=results,
            warnings=warnings,
        )


def _degraded_plan_without_rerank(plan: RetrievalPlan) -> RetrievalPlan:
    return RetrievalPlan(
        branches=plan.branches,
        fusion_enabled=plan.fusion_enabled,
        rerank_enabled=False,
    )


def _mode_without_rerank(mode: RetrievalMode) -> RetrievalMode:
    if mode in {RetrievalMode.C, RetrievalMode.D}:
        return RetrievalMode.A if mode == RetrievalMode.C else RetrievalMode.B
    return mode
