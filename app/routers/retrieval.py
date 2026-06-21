"""Production retrieval API with modes A/B/C/D."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.lexical_search_repository import LexicalSearchRepository
from app.embedding_pipeline.rerank import Reranker, build_reranker
from app.embedding_pipeline.retrieval_schemas import RetrievalRequest, RetrievalResponse
from app.embedding_pipeline.retrieval_service import (
    RetrievalMode,
    RetrievalService,
    parse_retrieval_mode,
)
from app.embedding_pipeline.search_repository import SemanticSearchRepository

router = APIRouter(tags=["retrieval"])
logger = logging.getLogger(__name__)
_service = RetrievalService()


def get_embedder(settings: Annotated[Settings, Depends(get_settings)]) -> OpenAIEmbedder:
    return OpenAIEmbedder(settings)


def get_vector_repository() -> SemanticSearchRepository:
    return SemanticSearchRepository()


def get_lexical_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LexicalSearchRepository:
    return LexicalSearchRepository(
        text_search_config=settings.retrieval_lexical_text_search_config,
    )


def get_reranker(settings: Annotated[Settings, Depends(get_settings)]) -> Reranker:
    return build_reranker(settings)


@router.post("/retrieval", response_model=RetrievalResponse)
async def retrieve_chunks(
    request: RetrievalRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
    vector_repository: Annotated[SemanticSearchRepository, Depends(get_vector_repository)],
    lexical_repository: Annotated[LexicalSearchRepository, Depends(get_lexical_repository)],
) -> RetrievalResponse:
    """Run production retrieval in mode A/B/C/D."""

    request_id = f"rtv_{uuid4().hex[:12]}"
    mode_raw = request.mode or settings.retrieval_default_mode
    try:
        mode = parse_retrieval_mode(mode_raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    recall_k = request.recall_k or settings.retrieval_recall_k
    top_k_final = request.top_k_final or settings.retrieval_top_k_final

    try:
        return await _service.retrieve(
            request.query,
            mode=mode,
            recall_k=recall_k,
            top_k_final=top_k_final,
            session=session,
            embedder=embedder,
            reranker=reranker,
            settings=settings,
            vector_repository=vector_repository,
            lexical_repository=lexical_repository,
        )
    except Exception as exc:
        logger.error(
            "retrieval_failed",
            extra={
                "request_id": request_id,
                "mode": mode.value,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to complete retrieval.",
        ) from exc
