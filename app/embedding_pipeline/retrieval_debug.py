"""Service helpers for explainable retrieval debug responses."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.lexical_search_repository import (
    LexicalSearchRepository,
    LexicalSearchResult,
)
from app.embedding_pipeline.retrieval_debug_repository import RetrievalDebugRepository
from app.embedding_pipeline.retrieval_debug_schemas import (
    BranchResultEntry,
    BranchesContainer,
    ChunkInspectionResponse,
    DebugResult,
    ResultExplanation,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
)
from app.embedding_pipeline.schemas import SearchResult
from app.embedding_pipeline.search_repository import SemanticSearchRepository

_IMPLEMENTED_STRATEGIES = {"vector", "lexical"}
_FUTURE_STRATEGIES = ("hybrid", "rerank")


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
        return ["vector", *_FUTURE_STRATEGIES]
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
    return {
        "strategies": strategies,
        "vector": request.vector.model_dump(),
        "lexical": request.lexical.model_dump(),
        "max_results": request.max_results,
    }


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
    filtered_entries = filter_vector_branch_entries(branch_entries, threshold=threshold)
    final_results: list[DebugResult] = []
    for final_position, entry in enumerate(filtered_entries[:max_results], start=1):
        result = by_chunk_id[entry.chunk_id]
        lexical_entry = lexical_by_chunk_id.get(entry.chunk_id)
        source_strategies = ["vector"]
        explanation = build_vector_explanation(entry, threshold=threshold)
        if lexical_entry is not None:
            source_strategies.append("lexical")
            explanation = ResultExplanation(
                summary=f"{explanation.summary} Also exact lexical match from the full-text branch.",
                signals=[*explanation.signals, "lexical_exact_match"],
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
                explanation=explanation,
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
                explanation=build_lexical_explanation(entry),
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
    final_results: list[DebugResult] = []
    vector_ms = 0
    lexical_ms = 0

    async def run_vector_branch() -> tuple[list[SearchResult], list[BranchResultEntry], int]:
        vector_started = time.perf_counter()
        query_vector = await embedder.embed_one(request.query)
        search_results = await repo.search_chunks(
            session,
            query_vector=query_vector,
            k=request.vector.top_k,
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
        )
        return (
            results,
            build_lexical_branch_entries(results),
            int((time.perf_counter() - lexical_started) * 1000),
        )

    branch_tasks: list[tuple[str, Any]] = []
    if "vector" in strategies:
        branch_tasks.append(("vector", run_vector_branch()))
    if "lexical" in strategies:
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

    if vector_entries is not None:
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

    total_ms = int((time.perf_counter() - total_started) * 1000)
    return RetrievalDebugResponse(
        query=request.query,
        applied_config=_applied_config(request, strategies),
        timings_ms={"vector": vector_ms, "lexical": lexical_ms, "total": total_ms},
        warnings=warnings,
        branches=BranchesContainer(vector=vector_entries, lexical=lexical_entries),
        final_results=final_results,
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
    if distance is None:
        return response

    return response.model_copy(
        update={
            "distance": distance,
            "similarity": _clamp_score(1.0 - distance),
        }
    )
