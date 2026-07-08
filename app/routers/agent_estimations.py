"""Agentic estimation API (Session 12)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session
from app.deps import get_request_id
from app.embedding_pipeline.chunk_content_repository import ChunkContentRepository
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.lexical_search_repository import LexicalSearchRepository
from app.embedding_pipeline.rerank import Reranker, build_reranker
from app.embedding_pipeline.retrieval_service import RetrievalService
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.schemas.agent_estimation_response import AgentEstimateRequest, AgentEstimateResponse
from app.services.agentic.agent_loop import run_estimation_agent
from app.services.agentic.openai_client import get_async_openai_client
from app.services.agentic.retrieval_adapter import build_retrieval_backend

router = APIRouter(tags=["agent-estimation"])
logger = logging.getLogger(__name__)
_retrieval_service = RetrievalService()


def get_embedder(settings: Annotated[Settings, Depends(get_settings)]) -> OpenAIEmbedder:
    return OpenAIEmbedder(settings)


def get_reranker(settings: Annotated[Settings, Depends(get_settings)]) -> Reranker:
    return build_reranker(settings)


@router.post(
    "/estimate/agent",
    response_model=AgentEstimateResponse,
    summary="Run the Session 12 agentic estimation loop",
)
async def estimate_with_agent(
    payload: AgentEstimateRequest,
    request_id: Annotated[str, Depends(get_request_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
) -> AgentEstimateResponse:
    client = get_async_openai_client(settings)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key is not configured.",
        )

    model = payload.model or settings.agent_model
    reasoning_effort = payload.reasoning_effort or settings.agent_reasoning_effort
    max_iterations = payload.max_iterations or settings.agent_max_iterations

    backend = build_retrieval_backend(
        session=session,
        embedder=embedder,
        reranker=reranker,
        settings=settings,
        retrieval_service=_retrieval_service,
        content_repository=ChunkContentRepository(),
        vector_repository=SemanticSearchRepository(),
        lexical_repository=LexicalSearchRepository(
            text_search_config=settings.retrieval_lexical_text_search_config,
        ),
    )

    logger.info(
        "agent_estimate_request",
        extra={"request_id": request_id, "model": model},
    )
    outcome = await run_estimation_agent(
        payload.transcript,
        client=client,
        model=model,
        reasoning_effort=reasoning_effort,
        max_iterations=max_iterations,
        retrieval_backend=backend,
    )
    return AgentEstimateResponse(
        result=outcome.estimate,
        trace=outcome.trace,
        request_id=request_id,
        iterations=outcome.iterations,
        stopped_reason=outcome.stopped_reason,
        model=model,
    )
