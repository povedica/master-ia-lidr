"""Internal retrieval debug API over persisted chunk embeddings."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.retrieval_debug import (
    inspect_retrieval_debug_chunk,
    run_retrieval_debug,
)
from app.embedding_pipeline.retrieval_debug_repository import RetrievalDebugRepository
from app.embedding_pipeline.retrieval_debug_schemas import (
    ChunkInspectionResponse,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
)
from app.embedding_pipeline.search_repository import SemanticSearchRepository

router = APIRouter(tags=["retrieval-debug"])
logger = logging.getLogger(__name__)


def get_embedder(settings: Annotated[Settings, Depends(get_settings)]) -> OpenAIEmbedder:
    return OpenAIEmbedder(settings)


def get_search_repository() -> SemanticSearchRepository:
    return SemanticSearchRepository()


def get_retrieval_debug_repository() -> RetrievalDebugRepository:
    return RetrievalDebugRepository()


@router.post("/retrieval-debug", response_model=RetrievalDebugResponse)
async def retrieval_debug(
    request: RetrievalDebugRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    repository: Annotated[SemanticSearchRepository, Depends(get_search_repository)],
) -> RetrievalDebugResponse:
    """Return an explainable vector retrieval trace for internal debugging."""

    request_id = f"rdbg_{uuid4().hex[:12]}"
    try:
        response = await run_retrieval_debug(
            request,
            session=session,
            embedder=embedder,
            repository=repository,
        )
        logger.info(
            "retrieval_debug_completed",
            extra={
                "request_id": request_id,
                "strategies": request.strategies,
                "vector_result_count": len(response.branches.vector or []),
                "timings_ms": response.timings_ms,
                "max_results": request.max_results,
            },
        )
        return response
    except Exception as exc:
        logger.error(
            "retrieval_debug_failed",
            extra={
                "request_id": request_id,
                "strategies": request.strategies,
                "max_results": request.max_results,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to complete retrieval debug.",
        ) from exc


@router.get(
    "/retrieval-debug/chunks/{chunk_id}",
    response_model=ChunkInspectionResponse,
)
async def inspect_chunk(
    chunk_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    repository: Annotated[RetrievalDebugRepository, Depends(get_retrieval_debug_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    query: Annotated[str | None, Query()] = None,
) -> ChunkInspectionResponse:
    """Inspect a persisted chunk, neighbors, parent document, and optional similarity."""

    try:
        response = await inspect_retrieval_debug_chunk(
            chunk_id=chunk_id,
            query=query,
            session=session,
            embedder=embedder,
            repository=repository,
            embedding_model=settings.embedding_pipeline_model,
        )
    except Exception as exc:
        logger.error(
            "retrieval_debug_chunk_inspection_failed",
            extra={
                "chunk_id": chunk_id,
                "query_present": bool((query or "").strip()),
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to inspect chunk.",
        ) from exc

    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chunk not found.",
        )
    return response
