"""Advanced StageConfig-driven retrieval API (feature-061)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session
from app.deps import get_request_id
from app.embedding_pipeline.advanced_retrieval import advanced_retrieve
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.lexical_search_repository import LexicalSearchRepository
from app.embedding_pipeline.rerank import Reranker, build_reranker
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.middleware.rate_limiting import conditional_rate_limit
from app.middleware.security import require_retrieval_key
from app.routers.retrieval import get_effective_settings
from app.schemas.retrieval_advanced import (
    AdvancedRetrievalRequest,
    AdvancedRetrievalResponse,
    resolve_request_config,
)

router = APIRouter(tags=["retrieval"])
logger = logging.getLogger(__name__)


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


def get_reranker(settings: Annotated[Settings, Depends(get_effective_settings)]) -> Reranker:
    return build_reranker(settings)


@router.post(
    "/retrieval/advanced",
    response_model=AdvancedRetrievalResponse,
    dependencies=[Depends(require_retrieval_key)],
)
@conditional_rate_limit("120/minute")
async def retrieve_advanced(
    request: Request,
    payload: AdvancedRetrievalRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_effective_settings)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
    vector_repository: Annotated[SemanticSearchRepository, Depends(get_vector_repository)],
    lexical_repository: Annotated[LexicalSearchRepository, Depends(get_lexical_repository)],
) -> AdvancedRetrievalResponse:
    """Run StageConfig-driven advanced retrieval over the budgets collection stub."""

    request_id = get_request_id(request)
    stage_config = resolve_request_config(payload)
    recall_k = payload.recall_k or settings.retrieval_recall_k
    top_k_final = payload.top_k_final or settings.retrieval_top_k_final

    try:
        service_response = await advanced_retrieve(
            session,
            payload.query,
            stage_config,
            recall_k=recall_k,
            top_k_final=top_k_final,
            embedder=embedder,
            reranker=reranker,
            settings=settings,
            vector_repository=vector_repository,
            lexical_repository=lexical_repository,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(
            "advanced_retrieval_failed",
            extra={
                "request_id": request_id,
                "search_mode": stage_config.search_mode,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to complete advanced retrieval.",
        ) from exc

    return AdvancedRetrievalResponse.from_service_response(service_response)
