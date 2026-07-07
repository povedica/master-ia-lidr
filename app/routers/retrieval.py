"""Production retrieval API with modes A/B/C/D."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session
from app.deps import get_request_id
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.lexical_search_repository import LexicalSearchRepository
from app.embedding_pipeline.rerank import Reranker, build_reranker
from app.embedding_pipeline.retrieval_schemas import RetrievalRequest, RetrievalResponse
from app.embedding_pipeline.retrieval_service import (
    RetrievalService,
    parse_retrieval_mode,
)
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.middleware.rate_limiting import conditional_rate_limit
from app.middleware.security import require_retrieval_key
from app.routers.runtime_config import get_runtime_redis_client
from app.services.runtime_config import get_effective_retrieval_config

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


async def get_effective_settings(
    settings: Annotated[Settings, Depends(get_settings)],
    redis_client: Annotated[Any, Depends(get_runtime_redis_client)],
) -> Settings:
    """Resolve ``Settings`` with runtime Redis overrides applied (feature-057).

    Only ``retrieval_rerank_enabled`` is wired here; other retrieval fields
    stay on env defaults until a later slice needs the override.
    """

    effective = await get_effective_retrieval_config(settings, redis_client)
    if effective.rerank_enabled == settings.retrieval_rerank_enabled:
        return settings
    return settings.model_copy(update={"retrieval_rerank_enabled": effective.rerank_enabled})


def get_reranker(settings: Annotated[Settings, Depends(get_effective_settings)]) -> Reranker:
    return build_reranker(settings)


@router.post(
    "/retrieval",
    response_model=RetrievalResponse,
    dependencies=[Depends(require_retrieval_key)],
)
@conditional_rate_limit("120/minute")
async def retrieve_chunks(
    request: Request,
    payload: RetrievalRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_effective_settings)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
    vector_repository: Annotated[SemanticSearchRepository, Depends(get_vector_repository)],
    lexical_repository: Annotated[LexicalSearchRepository, Depends(get_lexical_repository)],
) -> RetrievalResponse:
    """Run production retrieval in mode A/B/C/D."""

    request_id = get_request_id(request)
    mode_raw = payload.mode or settings.retrieval_default_mode
    try:
        mode = parse_retrieval_mode(mode_raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    recall_k = payload.recall_k or settings.retrieval_recall_k
    top_k_final = payload.top_k_final or settings.retrieval_top_k_final

    try:
        return await _service.retrieve(
            payload.query,
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
