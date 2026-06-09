"""Embedding pipeline ingest API."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.schemas import IngestRequest, IngestResponse, IngestStats

router = APIRouter(tags=["embeddings"])
logger = logging.getLogger(__name__)


def get_chunker(
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONStructuralChunker:
    model = settings.embedding_pipeline_model.strip() or "text-embedding-3-small"
    return JSONStructuralChunker(embedding_model=model)


def get_embedder(settings: Annotated[Settings, Depends(get_settings)]) -> OpenAIEmbedder:
    return OpenAIEmbedder(settings)


@router.post("/embeddings/ingest", response_model=IngestResponse)
async def ingest_embeddings(
    request: IngestRequest,
    chunker: Annotated[JSONStructuralChunker, Depends(get_chunker)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
) -> IngestResponse:
    """Chunk budgets, embed each chunk, and return vectors with aggregate stats."""

    request_id = f"emb_{uuid4().hex[:12]}"
    try:
        chunks = chunker.chunk(request.budgets)
        embedded = await embedder.embed_many(chunks)
        return IngestResponse(
            chunks=embedded,
            stats=IngestStats(
                total_budgets=len(request.budgets),
                total_chunks=len(embedded),
                total_tokens=embedder.last_total_tokens,
                estimated_cost_usd=embedder.last_cost_usd,
            ),
        )
    except Exception as exc:
        logger.error(
            "embedding_ingest_failed",
            extra={
                "request_id": request_id,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to embed budgets.",
        ) from exc
