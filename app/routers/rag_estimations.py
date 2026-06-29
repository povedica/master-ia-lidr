"""Grounded RAG estimation API."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.lexical_search_repository import LexicalSearchRepository
from app.embedding_pipeline.rerank import Reranker, build_reranker
from app.embedding_pipeline.retrieval_service import RetrievalService, parse_retrieval_mode
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.schemas.citation_report import CitationLineStatus
from app.schemas.estimations import UsageView
from app.schemas.rag_estimation_response import (
    CitationSummaryView,
    RagEstimateRequest,
    RagEstimationResponse,
)
from app.services.llm_chain import build_provider_chain
from app.services.rag_estimation_service import RagEstimationOutcome, RagEstimationService
from app.services.structured_llm_client import StructuredCompletionError

router = APIRouter(tags=["rag-estimation"])
logger = logging.getLogger(__name__)
_retrieval_service = RetrievalService()


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


def get_rag_estimation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RagEstimationService:
    from app.embedding_pipeline.chunk_content_repository import ChunkContentRepository

    return RagEstimationService(
        settings=settings,
        retrieval_service=_retrieval_service,
        content_repository=ChunkContentRepository(),
        providers=build_provider_chain(settings),
    )


def _citation_summary(outcome: RagEstimationOutcome) -> CitationSummaryView:
    counts = outcome.report.counts
    return CitationSummaryView(
        grounded_ok=counts.get(CitationLineStatus.GROUNDED_OK, 0),
        dangling=counts.get(CitationLineStatus.DANGLING_CITATION, 0),
        insufficient=counts.get(CitationLineStatus.INSUFFICIENT_DATA, 0),
        integrity_violations=counts.get(CitationLineStatus.INTEGRITY_VIOLATION, 0),
        has_dangling=outcome.report.has_dangling,
    )


def _usage_view(outcome: RagEstimationOutcome) -> UsageView | None:
    if outcome.usage is None:
        return None
    return UsageView(
        prompt_tokens=outcome.usage.prompt_tokens,
        completion_tokens=outcome.usage.completion_tokens,
        total_tokens=outcome.usage.total_tokens,
    )


@router.post("/estimate/rag", response_model=RagEstimationResponse)
async def estimate_rag(
    request: RagEstimateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
    vector_repository: Annotated[SemanticSearchRepository, Depends(get_vector_repository)],
    lexical_repository: Annotated[LexicalSearchRepository, Depends(get_lexical_repository)],
    service: Annotated[RagEstimationService, Depends(get_rag_estimation_service)],
) -> RagEstimationResponse:
    """Generate a grounded estimation with per-line citations from retrieved chunks."""

    request_id = f"rag_{uuid4().hex[:12]}"
    mode_raw = request.mode or settings.rag_estimation_retrieval_mode
    try:
        mode = parse_retrieval_mode(mode_raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    recall_k = request.recall_k or settings.retrieval_recall_k
    top_k_final = request.top_k_final or settings.retrieval_top_k_final
    started = perf_counter()

    try:
        outcome = await service.estimate(
            request.question,
            request_id=request_id,
            session=session,
            embedder=embedder,
            reranker=reranker,
            mode=mode,
            recall_k=recall_k,
            top_k_final=top_k_final,
            vector_repository=vector_repository,
            lexical_repository=lexical_repository,
        )
    except StructuredCompletionError as exc:
        logger.warning(
            "rag_estimation_failed",
            extra={"request_id": request_id, "error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Structured generation is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception(
            "rag_estimation_unexpected_error",
            extra={"request_id": request_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred.",
        ) from exc

    latency_ms = int((perf_counter() - started) * 1000)
    return RagEstimationResponse(
        result=outcome.result,
        citation_summary=_citation_summary(outcome),
        request_id=request_id,
        model=outcome.model,
        provider=outcome.provider,
        latency_ms=latency_ms,
        usage=_usage_view(outcome),
    )
