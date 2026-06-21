"""Service helpers for explainable retrieval debug responses."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.fusion import (
    RankingDiff,
    build_explanation,
    build_ranking_diff,
    reciprocal_rank_fusion,
    weighted_fusion,
)
from app.embedding_pipeline.lexical_search_repository import (
    LexicalSearchRepository,
    LexicalSearchResult,
)
from app.embedding_pipeline.rerank import (
    NoOpReranker,
    RerankCandidate,
    RerankedItem,
    Reranker,
)
from app.embedding_pipeline.retrieval_debug_repository import RetrievalDebugRepository
from app.embedding_pipeline.retrieval_debug_schemas import (
    BranchResultEntry,
    BranchesContainer,
    ChunkInspectionResponse,
    DebugResult,
    RankingDiffEntryResponse,
    RankingDiffResponse,
    RankingMoverResponse,
    ResultExplanation,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
)
from app.embedding_pipeline.schemas import SearchResult
from app.embedding_pipeline.search_repository import SemanticSearchRepository

_IMPLEMENTED_STRATEGIES = {"vector", "lexical", "hybrid", "rerank"}
_FUTURE_STRATEGIES: tuple[str, ...] = ()
_DIFF_BIG_MOVER_THRESHOLD = 3
_DIFF_RESCUE_RANK_THRESHOLD = 3
_NOOP_RERANK_WARNING = (
    "rerank.enabled=true but no reranker configured; rerank is a no-op placeholder"
)


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def build_vector_branch_entries(results: list[SearchResult]) -> list[BranchResultEntry]:
    """Expose existing semantic-search results as ranked vector-branch entries."""

    return [
        BranchResultEntry(
            rank=index,
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            score=_clamp_score(1.0 - result.distance),
            distance=result.distance,
        )
        for index, result in enumerate(results, start=1)
    ]


def filter_vector_branch_entries(
    entries: list[BranchResultEntry],
    *,
    threshold: float | None,
) -> list[BranchResultEntry]:
    """Keep vector entries whose normalized score satisfies the optional threshold."""

    if threshold is None:
        return entries
    return [entry for entry in entries if entry.score >= threshold]


def build_lexical_branch_entries(results: list[LexicalSearchResult]) -> list[BranchResultEntry]:
    """Expose ranked full-text results as normalized lexical-branch entries."""

    if not results:
        return []

    ranks = [result.ts_rank for result in results]
    min_rank = min(ranks)
    max_rank = max(ranks)
    rank_range = max_rank - min_rank

    def normalized_score(ts_rank: float) -> float:
        if rank_range == 0:
            return 1.0
        return _clamp_score((ts_rank - min_rank) / rank_range)

    return [
        BranchResultEntry(
            rank=index,
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            score=normalized_score(result.ts_rank),
            matched_terms=result.matched_terms,
        )
        for index, result in enumerate(results, start=1)
    ]


def build_vector_explanation(
    entry: BranchResultEntry,
    *,
    threshold: float | None = None,
) -> ResultExplanation:
    """Build a vector-only explanation with stable debug signal names."""

    signals = ["semantic_strong" if entry.distance <= 0.4 else "semantic_weak"]
    if threshold is not None and entry.score < threshold:
        signals.append("below_threshold")

    if signals[0] == "semantic_strong":
        summary = "strong semantic match from the vector branch."
    else:
        summary = "weaker semantic match from the vector branch."
    if "below_threshold" in signals:
        summary = f"{summary} Similarity is below the configured threshold."

    return ResultExplanation(summary=summary, signals=signals)


def build_lexical_explanation(entry: BranchResultEntry) -> ResultExplanation:
    """Build a lexical-only explanation with stable debug signal names."""

    if entry.matched_terms:
        terms = ", ".join(entry.matched_terms)
        summary = f"exact lexical match from the full-text branch on: {terms}."
    else:
        summary = "lexical match from the full-text branch."
    return ResultExplanation(summary=summary, signals=["lexical_exact_match"])


def _resolved_strategies(strategies: list[str]) -> list[str]:
    if strategies == ["all"]:
        return ["vector", "lexical", "hybrid", *_FUTURE_STRATEGIES]
    return strategies


def _derive_title(result: SearchResult | LexicalSearchResult) -> str:
    budget_id = result.metadata.get("budget_id")
    component_id = result.metadata.get("component_id")
    if budget_id and component_id:
        return f"{budget_id} {component_id}"
    if budget_id:
        return str(budget_id)
    source_path = result.metadata.get("source_path")
    if source_path:
        return str(source_path)
    return f"chunk {result.chunk_id}"


def _content_excerpt(content: str, *, max_chars: int = 240) -> str:
    stripped = " ".join(content.split())
    if len(stripped) <= max_chars:
        return stripped
    return f"{stripped[: max_chars - 1].rstrip()}..."


def _applied_config(request: RetrievalDebugRequest, strategies: list[str]) -> dict[str, Any]:
    config = {
        "strategies": strategies,
        "vector": request.vector.model_dump(),
        "lexical": request.lexical.model_dump(),
        "hybrid": request.hybrid.model_dump(),
        "rerank": request.rerank.model_dump(),
        "max_results": request.max_results,
    }
    if request.filters is not None:
        config["filters"] = request.filters.model_dump(exclude_none=True)
    return config


def _branch_entries_for_explanation(
    *,
    vector_entries: list[BranchResultEntry] | None,
    lexical_entries: list[BranchResultEntry] | None,
) -> dict[str, list[BranchResultEntry]]:
    branches: dict[str, list[BranchResultEntry]] = {}
    if vector_entries is not None:
        branches["vector"] = vector_entries
    if lexical_entries is not None:
        branches["lexical"] = lexical_entries
    return branches


def _source_strategies_for_chunk(
    chunk_id: int,
    *,
    vector_entries: list[BranchResultEntry] | None,
    lexical_entries: list[BranchResultEntry] | None,
    hybrid: bool,
) -> list[str]:
    source_strategies = []
    if vector_entries is not None and any(entry.chunk_id == chunk_id for entry in vector_entries):
        source_strategies.append("vector")
    if lexical_entries is not None and any(entry.chunk_id == chunk_id for entry in lexical_entries):
        source_strategies.append("lexical")
    if hybrid:
        source_strategies.append("hybrid")
    return source_strategies


def _threshold_drop_ids(
    entries: list[BranchResultEntry] | None,
    *,
    threshold: float | None,
) -> list[int]:
    if entries is None or threshold is None:
        return []
    return [entry.chunk_id for entry in entries if entry.score < threshold]


def _ranking_diff_response(diff: RankingDiff) -> RankingDiffResponse:
    def entry_response(entry: Any) -> RankingDiffEntryResponse:
        return RankingDiffEntryResponse(
            chunk_id=entry.chunk_id,
            document_id=entry.document_id,
            source_strategies=entry.source_strategies,
            branch_ranks=entry.branch_ranks,
        )

    return RankingDiffResponse(
        common=[entry_response(entry) for entry in diff.common],
        vector_only=[entry_response(entry) for entry in diff.vector_only],
        lexical_only=[entry_response(entry) for entry in diff.lexical_only],
        hybrid_rescued=[entry_response(entry) for entry in diff.hybrid_rescued],
        big_movers=[
            RankingMoverResponse(
                chunk_id=mover.chunk_id,
                document_id=mover.document_id,
                from_rank=mover.from_rank,
                to_rank=mover.to_rank,
                delta=mover.delta,
            )
            for mover in diff.big_movers
        ],
        dropped_by_threshold=[
            entry_response(entry)
            for entry in diff.dropped_by_threshold
        ],
        dropped_by_rerank=[
            entry_response(entry)
            for entry in diff.dropped_by_rerank
        ],
    )


def _rerank_score_source(result: DebugResult) -> float:
    for score in (result.fusion_score, result.semantic_score, result.lexical_score):
        if score is not None:
            return score
    return 0.0


def _rerank_candidates(final_results: list[DebugResult]) -> list[RerankCandidate]:
    return [
        RerankCandidate(
            entry=BranchResultEntry(
                rank=result.final_position,
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                score=_rerank_score_source(result),
            ),
            content=result.content_excerpt,
            metadata=result.metadata,
        )
        for result in final_results
    ]


def _rerank_branch_entries(reranked_items: list[RerankedItem]) -> list[BranchResultEntry]:
    return [
        BranchResultEntry(
            rank=item.rerank_rank,
            chunk_id=item.candidate.entry.chunk_id,
            document_id=item.candidate.entry.document_id,
            score=(
                item.rerank_score
                if item.rerank_score is not None
                else item.candidate.entry.score
            ),
        )
        for item in reranked_items
    ]


def _rerank_dropped_ids(
    candidates: list[RerankCandidate],
    reranked_items: list[RerankedItem],
) -> list[int]:
    returned_ids = {
        item.candidate.entry.chunk_id
        for item in reranked_items
    }
    return [
        candidate.entry.chunk_id
        for candidate in candidates
        if candidate.entry.chunk_id not in returned_ids
    ]


def _rerank_signal(
    *,
    original_rank: int,
    rerank_rank: int,
) -> tuple[str, str] | None:
    if rerank_rank < original_rank:
        return ("rerank_promoted", "promoted by rerank")
    if rerank_rank > original_rank:
        return ("rerank_demoted", "demoted by rerank")
    return None


def _apply_rerank_to_final_results(
    final_results: list[DebugResult],
    reranked_items: list[RerankedItem],
) -> list[DebugResult]:
    results_by_chunk_id = {
        result.chunk_id: result
        for result in final_results
    }
    reranked_results: list[DebugResult] = []
    for final_position, item in enumerate(reranked_items, start=1):
        result = results_by_chunk_id[item.candidate.entry.chunk_id]
        source_strategies = list(result.source_strategies)
        if "rerank" not in source_strategies:
            source_strategies.append("rerank")

        signals = list(result.explanation.signals)
        summary = result.explanation.summary
        rerank_signal = _rerank_signal(
            original_rank=item.candidate.entry.rank,
            rerank_rank=item.rerank_rank,
        )
        if rerank_signal is not None:
            signal, summary_part = rerank_signal
            if signal not in signals:
                signals.append(signal)
            summary = f"{summary.rstrip('.')}; {summary_part}."

        reranked_results.append(
            result.model_copy(
                update={
                    "final_position": final_position,
                    "rerank_score": item.rerank_score,
                    "rerank_rank": item.rerank_rank,
                    "source_strategies": source_strategies,
                    "explanation": ResultExplanation(
                        summary=summary,
                        signals=signals,
                    ),
                }
            )
        )
    return reranked_results


def _build_final_results(
    *,
    search_results: list[SearchResult],
    branch_entries: list[BranchResultEntry],
    threshold: float | None,
    max_results: int,
    lexical_entries: list[BranchResultEntry] | None = None,
) -> list[DebugResult]:
    by_chunk_id = {result.chunk_id: result for result in search_results}
    lexical_by_chunk_id = {
        entry.chunk_id: entry
        for entry in lexical_entries or []
    }
    explanation_branches = _branch_entries_for_explanation(
        vector_entries=branch_entries,
        lexical_entries=lexical_entries,
    )
    filtered_entries = filter_vector_branch_entries(branch_entries, threshold=threshold)
    final_results: list[DebugResult] = []
    for final_position, entry in enumerate(filtered_entries[:max_results], start=1):
        result = by_chunk_id[entry.chunk_id]
        lexical_entry = lexical_by_chunk_id.get(entry.chunk_id)
        source_strategies = _source_strategies_for_chunk(
            entry.chunk_id,
            vector_entries=branch_entries,
            lexical_entries=lexical_entries,
            hybrid=False,
        )
        final_results.append(
            DebugResult(
                final_position=final_position,
                chunk_id=entry.chunk_id,
                document_id=entry.document_id,
                title=_derive_title(result),
                content_excerpt=_content_excerpt(result.content),
                semantic_score=entry.score,
                semantic_rank=entry.rank,
                semantic_distance=entry.distance,
                lexical_score=lexical_entry.score if lexical_entry is not None else None,
                lexical_rank=lexical_entry.rank if lexical_entry is not None else None,
                matched_terms=lexical_entry.matched_terms if lexical_entry is not None else [],
                source_strategies=source_strategies,
                metadata=result.metadata,
                explanation=build_explanation(
                    entry,
                    branches=explanation_branches,
                    threshold=threshold,
                ),
            )
        )
    return final_results


def _build_lexical_final_results(
    *,
    lexical_results: list[LexicalSearchResult],
    branch_entries: list[BranchResultEntry],
    max_results: int,
) -> list[DebugResult]:
    by_chunk_id = {result.chunk_id: result for result in lexical_results}
    explanation_branches = {"lexical": branch_entries}
    final_results: list[DebugResult] = []
    for final_position, entry in enumerate(branch_entries[:max_results], start=1):
        result = by_chunk_id[entry.chunk_id]
        final_results.append(
            DebugResult(
                final_position=final_position,
                chunk_id=entry.chunk_id,
                document_id=entry.document_id,
                title=_derive_title(result),
                content_excerpt=_content_excerpt(result.content),
                lexical_score=entry.score,
                lexical_rank=entry.rank,
                matched_terms=entry.matched_terms,
                source_strategies=["lexical"],
                metadata=result.metadata,
                explanation=build_explanation(
                    entry,
                    branches=explanation_branches,
                ),
            )
        )
    return final_results


def _build_hybrid_final_results(
    *,
    hybrid_entries: list[BranchResultEntry],
    vector_results: list[SearchResult],
    lexical_results: list[LexicalSearchResult],
    vector_entries: list[BranchResultEntry] | None,
    lexical_entries: list[BranchResultEntry] | None,
    diff: RankingDiff,
    threshold: float | None,
    max_results: int,
) -> list[DebugResult]:
    vector_results_by_chunk_id = {result.chunk_id: result for result in vector_results}
    lexical_results_by_chunk_id = {result.chunk_id: result for result in lexical_results}
    vector_entries_by_chunk_id = {
        entry.chunk_id: entry
        for entry in vector_entries or []
    }
    lexical_entries_by_chunk_id = {
        entry.chunk_id: entry
        for entry in lexical_entries or []
    }
    explanation_branches = _branch_entries_for_explanation(
        vector_entries=vector_entries,
        lexical_entries=lexical_entries,
    )
    final_results: list[DebugResult] = []

    for final_position, entry in enumerate(hybrid_entries[:max_results], start=1):
        source_result = vector_results_by_chunk_id.get(entry.chunk_id) or lexical_results_by_chunk_id[entry.chunk_id]
        vector_entry = vector_entries_by_chunk_id.get(entry.chunk_id)
        lexical_entry = lexical_entries_by_chunk_id.get(entry.chunk_id)
        final_results.append(
            DebugResult(
                final_position=final_position,
                chunk_id=entry.chunk_id,
                document_id=entry.document_id,
                title=_derive_title(source_result),
                content_excerpt=_content_excerpt(source_result.content),
                semantic_score=vector_entry.score if vector_entry is not None else None,
                semantic_rank=vector_entry.rank if vector_entry is not None else None,
                semantic_distance=vector_entry.distance if vector_entry is not None else None,
                lexical_score=lexical_entry.score if lexical_entry is not None else None,
                lexical_rank=lexical_entry.rank if lexical_entry is not None else None,
                fusion_score=entry.score,
                fusion_rank=entry.rank,
                matched_terms=lexical_entry.matched_terms if lexical_entry is not None else [],
                source_strategies=_source_strategies_for_chunk(
                    entry.chunk_id,
                    vector_entries=vector_entries,
                    lexical_entries=lexical_entries,
                    hybrid=True,
                ),
                metadata=source_result.metadata,
                explanation=build_explanation(
                    entry,
                    branches=explanation_branches,
                    diff=diff,
                    threshold=threshold,
                ),
            )
        )
    return final_results


async def run_retrieval_debug(
    request: RetrievalDebugRequest,
    *,
    session: AsyncSession,
    embedder: OpenAIEmbedder,
    repository: SemanticSearchRepository | None = None,
    lexical_repository: LexicalSearchRepository | None = None,
    reranker: Reranker | None = None,
) -> RetrievalDebugResponse:
    """Run debug retrieval for implemented branches and return an explainable trace."""

    repo = repository or SemanticSearchRepository()
    lexical_repo = lexical_repository or LexicalSearchRepository()
    total_started = time.perf_counter()
    strategies = _resolved_strategies(request.strategies)
    warnings = [
        f"Strategy '{strategy}' is not implemented yet."
        for strategy in strategies
        if strategy not in _IMPLEMENTED_STRATEGIES
    ]

    vector_entries: list[BranchResultEntry] | None = None
    lexical_entries: list[BranchResultEntry] | None = None
    lexical_results: list[LexicalSearchResult] = []
    hybrid_entries: list[BranchResultEntry] | None = None
    rerank_entries: list[BranchResultEntry] | None = None
    diff: RankingDiff | None = None
    final_results: list[DebugResult] = []
    vector_ms = 0
    lexical_ms = 0
    hybrid_ms = 0
    rerank_ms = 0

    async def run_vector_branch() -> tuple[list[SearchResult], list[BranchResultEntry], int]:
        vector_started = time.perf_counter()
        query_vector = await embedder.embed_one(request.query)
        search_results = await repo.search_chunks(
            session,
            query_vector=query_vector,
            k=request.vector.top_k,
            filters=request.filters,
        )
        return (
            search_results,
            build_vector_branch_entries(search_results),
            int((time.perf_counter() - vector_started) * 1000),
        )

    async def run_lexical_branch() -> tuple[list[LexicalSearchResult], list[BranchResultEntry], int]:
        lexical_started = time.perf_counter()
        results = await lexical_repo.search_chunks(
            session,
            query=request.query,
            top_k=request.lexical.top_k,
            filters=request.filters,
        )
        return (
            results,
            build_lexical_branch_entries(results),
            int((time.perf_counter() - lexical_started) * 1000),
        )

    branch_tasks: list[tuple[str, Any]] = []
    hybrid_requested = "hybrid" in strategies and request.hybrid.enabled
    if "vector" in strategies or hybrid_requested:
        branch_tasks.append(("vector", run_vector_branch()))
    if "lexical" in strategies or hybrid_requested:
        branch_tasks.append(("lexical", run_lexical_branch()))

    vector_results: list[SearchResult] = []
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

    threshold_drop_ids = _threshold_drop_ids(
        vector_entries,
        threshold=request.vector.threshold,
    )
    if hybrid_requested and vector_entries is not None and lexical_entries is not None:
        hybrid_started = time.perf_counter()
        filtered_vector_entries = filter_vector_branch_entries(
            vector_entries,
            threshold=request.vector.threshold,
        )
        fusion_branches = {
            "vector": filtered_vector_entries,
            "lexical": lexical_entries,
        }
        if request.hybrid.method == "weighted":
            hybrid_entries = weighted_fusion(
                fusion_branches,
                weights=request.hybrid.weights or {},
            )
        else:
            hybrid_entries = reciprocal_rank_fusion(
                fusion_branches,
                k=request.hybrid.rrf_k,
                weights=request.hybrid.weights,
            )
        diff = build_ranking_diff(
            {
                "vector": vector_entries,
                "lexical": lexical_entries,
            },
            hybrid_entries[: request.max_results],
            threshold_drops=threshold_drop_ids,
            big_mover_threshold=_DIFF_BIG_MOVER_THRESHOLD,
            rescue_rank_threshold=_DIFF_RESCUE_RANK_THRESHOLD,
        )
        final_results = _build_hybrid_final_results(
            hybrid_entries=hybrid_entries,
            vector_results=vector_results,
            lexical_results=lexical_results,
            vector_entries=vector_entries,
            lexical_entries=lexical_entries,
            diff=diff,
            threshold=request.vector.threshold,
            max_results=request.max_results,
        )
        hybrid_ms = int((time.perf_counter() - hybrid_started) * 1000)
    elif vector_entries is not None:
        final_results = _build_final_results(
            search_results=vector_results,
            branch_entries=vector_entries,
            threshold=request.vector.threshold,
            max_results=request.max_results,
            lexical_entries=lexical_entries,
        )
    elif lexical_entries is not None:
        final_results = _build_lexical_final_results(
            lexical_results=lexical_results,
            branch_entries=lexical_entries,
            max_results=request.max_results,
        )

    if request.rerank.enabled and final_results:
        rerank_started = time.perf_counter()
        active_reranker = reranker or NoOpReranker()
        candidates = _rerank_candidates(final_results)
        reranked_items = await active_reranker.rerank(request.query, candidates)
        rerank_entries = _rerank_branch_entries(reranked_items)
        rerank_drop_ids = _rerank_dropped_ids(candidates, reranked_items)
        final_results = _apply_rerank_to_final_results(final_results, reranked_items)
        if active_reranker.is_noop:
            warnings.append(_NOOP_RERANK_WARNING)
        if diff is not None and vector_entries is not None and lexical_entries is not None:
            diff = build_ranking_diff(
                {
                    "vector": vector_entries,
                    "lexical": lexical_entries,
                },
                rerank_entries,
                threshold_drops=threshold_drop_ids,
                rerank_drops=rerank_drop_ids,
                big_mover_threshold=_DIFF_BIG_MOVER_THRESHOLD,
                rescue_rank_threshold=_DIFF_RESCUE_RANK_THRESHOLD,
            )
        rerank_ms = int((time.perf_counter() - rerank_started) * 1000)

    total_ms = int((time.perf_counter() - total_started) * 1000)
    return RetrievalDebugResponse(
        query=request.query,
        applied_config=_applied_config(request, strategies),
        timings_ms={
            "vector": vector_ms,
            "lexical": lexical_ms,
            "hybrid": hybrid_ms,
            "rerank": rerank_ms,
            "total": total_ms,
        },
        warnings=warnings,
        branches=BranchesContainer(
            vector=vector_entries,
            lexical=lexical_entries,
            hybrid=hybrid_entries,
            rerank=rerank_entries,
        ),
        final_results=final_results,
        diff=_ranking_diff_response(diff) if diff is not None else None,
    )


async def inspect_retrieval_debug_chunk(
    *,
    chunk_id: int,
    query: str | None,
    session: AsyncSession,
    embedder: OpenAIEmbedder,
    repository: RetrievalDebugRepository,
    embedding_model: str,
) -> ChunkInspectionResponse | None:
    """Return one chunk with document context and optional query similarity."""

    response = await repository.get_chunk_inspection(
        session,
        chunk_id=chunk_id,
        embedding_model=embedding_model,
    )
    if response is None:
        return None

    stripped_query = (query or "").strip()
    if not stripped_query:
        return response

    query_vector = await embedder.embed_one(stripped_query)
    distance = await repository.get_chunk_distance(
        session,
        chunk_id=chunk_id,
        query_vector=query_vector,
    )
    matched_terms = await repository.get_chunk_matched_terms(
        session,
        chunk_id=chunk_id,
        query=stripped_query,
    )
    if distance is None:
        return response.model_copy(update={"matched_terms": matched_terms})

    return response.model_copy(
        update={
            "distance": distance,
            "similarity": _clamp_score(1.0 - distance),
            "matched_terms": matched_terms,
        }
    )
