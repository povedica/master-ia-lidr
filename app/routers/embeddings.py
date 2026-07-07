"""Embedding pipeline ingest API."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session
from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.errors import DuplicateDocumentError
from app.embedding_pipeline.persistent_ingest import run_persistent_ingest
from app.embedding_pipeline.repository import EmbeddingIngestRepository
from app.embedding_pipeline.schemas import PersistentIngestRequest, PersistentIngestResponse
from app.schemas.embeddings_compare import (
    EmbeddingsCompareRequest,
    EmbeddingsCompareResponse,
    StrategyQueryPreviewView,
    StrategyStatsView,
)

router = APIRouter(tags=["embeddings"])
logger = logging.getLogger(__name__)


def get_chunker(
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONStructuralChunker:
    model = settings.embedding_pipeline_model.strip() or "text-embedding-3-small"
    return JSONStructuralChunker(embedding_model=model)


def get_embedder(settings: Annotated[Settings, Depends(get_settings)]) -> OpenAIEmbedder:
    return OpenAIEmbedder(settings)


def get_ingest_repository() -> EmbeddingIngestRepository:
    return EmbeddingIngestRepository()


@router.post("/embeddings/ingest", response_model=PersistentIngestResponse)
async def ingest_embeddings(
    request: PersistentIngestRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    chunker: Annotated[JSONStructuralChunker, Depends(get_chunker)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    repository: Annotated[EmbeddingIngestRepository, Depends(get_ingest_repository)],
) -> PersistentIngestResponse | JSONResponse:
    """Persist one budget document, chunk it, embed components, and return metadata."""

    request_id = f"emb_{uuid4().hex[:12]}"
    try:
        return await run_persistent_ingest(
            request,
            session=session,
            chunker=chunker,
            embedder=embedder,
            repository=repository,
        )
    except DuplicateDocumentError as exc:
        logger.info(
            "embedding_ingest_duplicate",
            extra={
                "request_id": request_id,
                "source_path": request.source_path,
                "document_type": request.document_type,
                "document_id": exc.document_id,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Document already ingested",
                "document_id": exc.document_id,
            },
        )
    except Exception as exc:
        logger.error(
            "embedding_ingest_failed",
            extra={
                "request_id": request_id,
                "source_path": request.source_path,
                "document_type": request.document_type,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to ingest budget document.",
        ) from exc


@router.post("/embeddings/compare", response_model=EmbeddingsCompareResponse)
async def compare_embeddings(
    payload: EmbeddingsCompareRequest,
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmbeddingsCompareResponse:
    """Compare chunking strategies on in-memory budgets (no persistence)."""

    from app.embedding_pipeline.chunking_compare import (
        SUPPORTED_STRATEGIES,
        compute_strategy_stats,
        preview_strategy_queries,
    )

    strategy_names = payload.strategies
    if strategy_names is None:
        strategy_names = [
            item.strip()
            for item in settings.chunking_compare_default_strategies.split(",")
            if item.strip()
        ]
    unknown = [name for name in strategy_names if name not in SUPPORTED_STRATEGIES]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown strategy: {unknown[0]}",
        )

    stats = [
        StrategyStatsView(**compute_strategy_stats(name, payload.budgets).__dict__)
        for name in strategy_names
    ]
    query_previews: list[StrategyQueryPreviewView] = []
    if payload.queries:
        for name in strategy_names:
            previews = await preview_strategy_queries(
                name,
                payload.budgets,
                payload.queries,
                embedder=embedder,
                top_k=payload.top_k,
            )
            query_previews.extend(
                StrategyQueryPreviewView(
                    strategy=preview.strategy,
                    query=preview.query,
                    top_chunks=preview.top_chunks,
                )
                for preview in previews
            )

    return EmbeddingsCompareResponse(
        stats_per_strategy=stats,
        queries_per_strategy=query_previews,
    )
