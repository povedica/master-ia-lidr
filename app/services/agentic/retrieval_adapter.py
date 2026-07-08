"""Map RetrievalService results to agent search_budgets items."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.embedding_pipeline.chunk_content_repository import ChunkContent, ChunkContentRepository
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.lexical_search_repository import LexicalSearchRepository
from app.embedding_pipeline.rerank import Reranker
from app.embedding_pipeline.retrieval_schemas import RetrievalResultRow
from app.embedding_pipeline.retrieval_service import RetrievalMode, RetrievalService, parse_retrieval_mode
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.services.agentic.agent_schemas import SearchBudgetsArgs
from app.services.agentic.agent_tools import CONTENT_PREVIEW_CHARS, RetrievalBackend

logger = logging.getLogger(__name__)


def _preview_text(content: str | None) -> str:
    if not content:
        return ""
    return " ".join(content.split())[:CONTENT_PREVIEW_CHARS]


def _distance_score(row: RetrievalResultRow) -> float:
    if row.rerank_score is not None:
        return round(float(row.rerank_score), 4)
    if row.fusion_score is not None:
        return round(float(row.fusion_score), 4)
    return round(float(row.score), 4)


def map_retrieval_row_to_item(
    row: RetrievalResultRow,
    content: ChunkContent | None,
) -> dict[str, Any]:
    """Map a retrieval row + optional chunk content to the stub-compatible item shape."""
    metadata = content.metadata if content is not None else row.metadata
    sector = metadata.get("client_sector") or metadata.get("sector") or "unknown"
    estimated_hours = metadata.get("estimated_hours")
    budget_id = row.budget_id or (content.budget_id if content else None) or metadata.get("budget_id")
    return {
        "id": row.chunk_id,
        "content_preview": _preview_text(content.content if content else None),
        "sector": str(sector),
        "budget_id": str(budget_id) if budget_id is not None else "",
        "estimated_hours": float(estimated_hours) if estimated_hours is not None else 0.0,
        "distance": _distance_score(row),
    }


def _sector_matches(item_sector: str, allowed: set[str]) -> bool:
    return item_sector.lower() in allowed


def build_retrieval_backend(
    *,
    session: AsyncSession,
    embedder: OpenAIEmbedder,
    reranker: Reranker,
    settings: Settings,
    retrieval_service: RetrievalService,
    content_repository: ChunkContentRepository,
    mode: RetrievalMode | None = None,
    vector_repository: SemanticSearchRepository | None = None,
    lexical_repository: LexicalSearchRepository | None = None,
) -> RetrievalBackend:
    """Build an async backend that wraps RetrievalService.retrieve()."""

    resolved_mode = mode or parse_retrieval_mode(
        settings.agent_retrieval_mode or settings.rag_estimation_retrieval_mode
    )

    async def backend(args: SearchBudgetsArgs) -> list[dict[str, Any]]:
        retrieval = await retrieval_service.retrieve(
            args.query,
            mode=resolved_mode,
            recall_k=settings.retrieval_recall_k,
            top_k_final=settings.retrieval_top_k_final,
            session=session,
            embedder=embedder,
            reranker=reranker,
            settings=settings,
            vector_repository=vector_repository,
            lexical_repository=lexical_repository,
        )
        contents = await content_repository.get_contents_by_ids(
            session,
            [row.chunk_id for row in retrieval.results],
        )
        items = [
            map_retrieval_row_to_item(row, contents.get(row.chunk_id))
            for row in retrieval.results
        ]
        sectors = None
        if args.filters and args.filters.sectors:
            sectors = {sector.lower() for sector in args.filters.sectors}
        if sectors:
            items = [item for item in items if _sector_matches(item["sector"], sectors)]
        logger.info(
            "agent_retrieval_backend_completed",
            extra={"query": args.query, "results": len(items)},
        )
        return items

    return backend


def load_stub_retrieval_backend() -> RetrievalBackend:
    """Load the offline Session 12 stub as a RetrievalBackend."""
    import importlib.util
    from pathlib import Path

    stub_path = Path(__file__).resolve().parents[3] / "exercises" / "session-12" / "reference_retrieval.py"
    spec = importlib.util.spec_from_file_location("session_12_reference_retrieval", stub_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load stub retrieval from {stub_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def stub_backend(args: SearchBudgetsArgs) -> list[dict[str, Any]]:
        filters = args.filters.model_dump() if args.filters else None
        return module.search_budgets_stub(args.query, filters)

    return stub_backend
