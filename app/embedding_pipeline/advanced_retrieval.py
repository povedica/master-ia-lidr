"""StageConfig-driven advanced retrieval orchestration (feature-061)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.fusion import reciprocal_rank_fusion
from app.embedding_pipeline.lexical_search_repository import (
    LexicalSearchRepository,
    LexicalSearchResult,
)
from app.embedding_pipeline.rerank import RerankCandidate, Reranker
from app.embedding_pipeline.query_transform import transform_query
from app.embedding_pipeline.retrieval_debug import (
    build_lexical_branch_entries,
    build_vector_branch_entries,
)
from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry
from app.embedding_pipeline.retrieval_debug_schemas import RetrievalMetadataFilters
from app.embedding_pipeline.retrieval_router import route_collection
from app.embedding_pipeline.retrieval_service import (
    RetrievalPlan,
    _content_and_metadata,
    _degraded_plan_without_rerank,
    _entry_maps,
    _normalize_rerank_scores,
    _source_strategies,
)
from app.embedding_pipeline.schemas import SearchResult
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.embedding_pipeline.stage_config import StageConfig
from app.embedding_pipeline.temporal_decay import apply_temporal_decay

logger = logging.getLogger(__name__)

_NOOP_RERANK_WARNING = (
    "rerank requested but no reranker configured; rerank is a no-op placeholder"
)
_RERANK_DISABLED_WARNING = "rerank disabled by RETRIEVAL_RERANK_ENABLED=false"


@dataclass(frozen=True)
class AdvancedRetrievalTimingsMs:
    vector: int = 0
    lexical: int = 0
    fusion: int = 0
    rerank: int = 0
    total: int = 0


@dataclass(frozen=True)
class AdvancedRetrievalRow:
    final_position: int
    chunk_id: int
    document_id: int
    collection: str
    budget_id: str | None
    score: float
    vector_score: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    matched_terms: list[str] = field(default_factory=list)
    source_strategies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdvancedRetrievalResponse:
    query: str
    config: StageConfig
    effective_config: StageConfig
    timings_ms: AdvancedRetrievalTimingsMs
    results: list[AdvancedRetrievalRow]
    warnings: list[str] = field(default_factory=list)


def resolve_stage_plan(config: StageConfig) -> RetrievalPlan:
    """Map ``StageConfig`` to the branch/fusion/rerank plan used by retrieval."""

    if config.search_mode == "vector":
        return RetrievalPlan(
            branches=("vector",),
            fusion_enabled=False,
            rerank_enabled=config.rerank,
        )
    if config.fusion != "rrf":
        raise ValueError(
            f"advanced_retrieve supports fusion='rrf' only in this slice; got {config.fusion!r}"
        )
    return RetrievalPlan(
        branches=("vector", "lexical"),
        fusion_enabled=True,
        rerank_enabled=config.rerank,
    )


async def advanced_retrieve(
    session: AsyncSession,
    query: str,
    config: StageConfig,
    *,
    recall_k: int,
    top_k_final: int,
    embedder: OpenAIEmbedder,
    reranker: Reranker,
    settings: Settings,
    vector_repository: SemanticSearchRepository | None = None,
    lexical_repository: LexicalSearchRepository | None = None,
    collection: str | None = None,
) -> AdvancedRetrievalResponse:
    """Run StageConfig-driven retrieval over the single ``chunks`` collection."""

    total_started = time.perf_counter()
    search_query = await transform_query(
        query,
        config_enabled=config.query_transform,
        settings_enabled=settings.query_transform_enabled,
    )
    collection = collection or route_collection(
        search_query,
        config_enabled=config.routing_enabled,
        settings_enabled=settings.retrieval_routing_enabled,
    )
    plan = resolve_stage_plan(config)
    warnings: list[str] = []
    effective_plan = plan
    effective_config = config

    rerank_requested = plan.rerank_enabled
    rerank_active = rerank_requested and settings.retrieval_rerank_enabled
    if rerank_requested and not settings.retrieval_rerank_enabled:
        warnings.append(_RERANK_DISABLED_WARNING)
        effective_plan = _degraded_plan_without_rerank(plan)
        effective_config = replace(config, rerank=False)
    elif rerank_requested and reranker.is_noop:
        warnings.append(_NOOP_RERANK_WARNING)
        effective_plan = _degraded_plan_without_rerank(plan)
        effective_config = replace(config, rerank=False)

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

    search_filters: RetrievalMetadataFilters | None = None
    if config.routing_enabled and settings.retrieval_routing_enabled:
        search_filters = RetrievalMetadataFilters(collection=collection)

    async def run_vector_branch() -> tuple[list[SearchResult], list[BranchResultEntry], int]:
        started = time.perf_counter()
        query_vector = await embedder.embed_one(search_query)
        results = await vector_repo.search_chunks(
            session,
            query_vector=query_vector,
            k=recall_k,
            filters=search_filters,
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
            query=search_query,
            top_k=recall_k,
            filters=search_filters,
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

    ordered_entries = apply_temporal_decay(
        ordered_entries,
        config_enabled=config.temporal_decay,
        settings_enabled=settings.retrieval_temporal_decay_enabled,
    )

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
            await reranker.rerank(search_query, candidates),
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

    results: list[AdvancedRetrievalRow] = []
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
            AdvancedRetrievalRow(
                final_position=position,
                chunk_id=entry.chunk_id,
                document_id=entry.document_id,
                collection=collection,
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
    logger.info(
        "advanced_retrieval_completed",
        extra={
            "search_mode": effective_config.search_mode,
            "rerank": effective_config.rerank,
            "vector_count": len(vector_entries or []),
            "lexical_count": len(lexical_entries or []),
            "final_count": len(results),
            "collection": collection,
        },
    )
    return AdvancedRetrievalResponse(
        query=query,
        config=config,
        effective_config=effective_config,
        timings_ms=AdvancedRetrievalTimingsMs(
            vector=vector_ms,
            lexical=lexical_ms,
            fusion=fusion_ms,
            rerank=rerank_ms,
            total=total_ms,
        ),
        results=results,
        warnings=warnings,
    )
