"""Semantic search API over persisted pgvector chunk embeddings."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.schemas import SearchRequest, SearchResponse
from app.embedding_pipeline.search import run_semantic_search
from app.embedding_pipeline.search_repository import SemanticSearchRepository

router = APIRouter(tags=["search"])
logger = logging.getLogger(__name__)


def get_embedder(settings: Annotated[Settings, Depends(get_settings)]) -> OpenAIEmbedder:
    return OpenAIEmbedder(settings)


def get_search_repository() -> SemanticSearchRepository:
    return SemanticSearchRepository()


@router.post("/search", response_model=SearchResponse)
async def search_chunks(
    request: SearchRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    repository: Annotated[SemanticSearchRepository, Depends(get_search_repository)],
) -> SearchResponse:
    """Embed the query and return top-k chunks ranked by cosine distance."""

    request_id = f"srch_{uuid4().hex[:12]}"
    try:
        return await run_semantic_search(
            request,
            session=session,
            embedder=embedder,
            repository=repository,
        )
    except Exception as exc:
        logger.error(
            "semantic_search_failed",
            extra={
                "request_id": request_id,
                "k": request.k,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to complete semantic search.",
        ) from exc
