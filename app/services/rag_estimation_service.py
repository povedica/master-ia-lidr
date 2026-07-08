"""Orchestrate grounded RAG estimation: retrieve → generate → verify citations."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.embedding_pipeline.chunk_content_repository import ChunkContentRepository
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.lexical_search_repository import LexicalSearchRepository
from app.embedding_pipeline.rerank import Reranker
from app.embedding_pipeline.rag_augmentation import augment_retrieval_chunks
from app.embedding_pipeline.retrieval_service import RetrievalMode, RetrievalService
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.schemas.citation_report import CitationLineStatus, CitationReport
from app.schemas.coherence_report import CoherenceReport
from app.schemas.estimation_query import compose_search_text
from app.schemas.hallucination_report import HallucinationReport
from app.schemas.rag_estimation_result import RagEstimationResult
from app.services.citation_verification import verify_citations
from app.services.rag_coherence import check_coherence
from app.services.rag_hallucination_gate import gate_estimate
from app.services.llm_types import LLMProvider, UsageInfo
from app.services.observability.bootstrap import get_observability
from app.services.provider_routing import resolve_first_litellm_route
from app.services.rag_context_assembler import (
    AssembledContext,
    assemble_rag_context,
    resolve_rag_context_encoding,
    truncate_assembled_context,
)
from app.services.rag_estimation_prompt_rendering import render_rag_estimation_prompt
from app.services.rag_query_reformulator import reformulate_query
from app.services.structured_llm_client import StructuredCompletionError, complete_structured

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RagEstimationOutcome:
    result: RagEstimationResult
    report: CitationReport
    coherence_report: CoherenceReport
    hallucination_report: HallucinationReport
    chunk_texts: list[str]
    model: str | None
    provider: str | None
    usage: UsageInfo | None
    finish_reason: str | None
    prompt_version: str


class RagEstimationService:
    """Retrieve context, generate grounded estimates, and audit citations."""

    def __init__(
        self,
        settings: Settings,
        retrieval_service: RetrievalService,
        content_repository: ChunkContentRepository,
        providers: list[LLMProvider],
    ) -> None:
        self._settings = settings
        self._retrieval_service = retrieval_service
        self._content_repository = content_repository
        self._providers = providers

    async def estimate(
        self,
        question: str,
        *,
        transcript: str | None = None,
        request_id: str,
        session: AsyncSession,
        embedder: OpenAIEmbedder,
        reranker: Reranker,
        mode: RetrievalMode,
        recall_k: int,
        top_k_final: int,
        vector_repository: SemanticSearchRepository | None = None,
        lexical_repository: LexicalSearchRepository | None = None,
    ) -> RagEstimationOutcome:
        observability = get_observability()
        with observability.start_span("rag_estimation.pipeline"):
            estimation_query = await reformulate_query(
                question,
                transcript=transcript,
                settings=self._settings,
                providers=self._providers,
            )
            search_text = compose_search_text(estimation_query)
            retrieval = await self._retrieval_service.retrieve(
                search_text,
                mode=mode,
                recall_k=recall_k,
                top_k_final=top_k_final,
                session=session,
                embedder=embedder,
                reranker=reranker,
                settings=self._settings,
                vector_repository=vector_repository,
                lexical_repository=lexical_repository,
            )

            if not retrieval.results:
                return await self._insufficient_context_outcome(request_id)

            contents = await self._content_repository.get_contents_by_ids(
                session,
                [row.chunk_id for row in retrieval.results],
            )
            rows = list(retrieval.results)
            if self._settings.augmentation_enabled:
                rows, contents = augment_retrieval_chunks(rows, contents)
            assembled = assemble_rag_context(rows, contents)
            assembled = truncate_assembled_context(
                assembled,
                max_tokens=self._settings.rag_context_max_tokens,
                encoding=resolve_rag_context_encoding(self._settings),
            )
            if not assembled.chunk_ids:
                return await self._insufficient_context_outcome(request_id)

            route = resolve_first_litellm_route(self._providers)
            if route is None:
                raise StructuredCompletionError(
                    "RAG estimation requires a live LiteLLM provider (configure OpenAI or Anthropic)."
                )

            rendered = render_rag_estimation_prompt(
                question=question,
                prompt_block=assembled.prompt_block,
            )
            try:
                result, usage, finish = await complete_structured(
                    litellm_model=route.litellm_model,
                    chain_provider=route.provider_name,
                    api_key=route.api_key,
                    timeout_seconds=route.timeout_seconds,
                    system_prompt=rendered.system_prompt,
                    user_prompt=rendered.user_prompt,
                    max_output_tokens=self._settings.estimation_output_tokens_max,
                    response_model=RagEstimationResult,
                    max_attempts=self._settings.structured_output_max_attempts,
                )
            except StructuredCompletionError:
                raise

            report = verify_citations(result, assembled.chunk_ids, request_id=request_id)
            self._log_citation_report(report)
            coherence_report = check_coherence(
                result,
                request_id=request_id,
                enabled=self._settings.rag_coherence_enabled,
                total_tolerance=self._settings.rag_coherence_total_tolerance,
            )
            hallucination_report = await gate_estimate(
                result,
                chunk_texts=assembled.chunk_texts,
                request_id=request_id,
                settings=self._settings,
                providers=self._providers,
                enabled=self._settings.hallucination_gate_enabled,
                judge_model=self._settings.hallucination_judge_model,
            )
            return RagEstimationOutcome(
                result=result,
                report=report,
                coherence_report=coherence_report,
                hallucination_report=hallucination_report,
                chunk_texts=assembled.chunk_texts,
                model=route.model,
                provider=route.provider_name,
                usage=usage,
                finish_reason=finish,
                prompt_version=rendered.prompt_version,
            )

    async def _insufficient_context_outcome(self, request_id: str) -> RagEstimationOutcome:
        logger.info(
            "rag_insufficient_context",
            extra={"request_id": request_id},
        )
        result = RagEstimationResult(
            summary=(
                "Insufficient retrieved context to produce a grounded estimation. "
                "No relevant budget chunks were available for this question."
            ),
            line_items=[],
            total_hours=0.0,
            insufficient_context=True,
        )
        report = verify_citations(result, set(), request_id=request_id)
        self._log_citation_report(report)
        coherence_report = check_coherence(
            result,
            request_id=request_id,
            enabled=self._settings.rag_coherence_enabled,
            total_tolerance=self._settings.rag_coherence_total_tolerance,
        )
        hallucination_report = await gate_estimate(
            result,
            chunk_texts=[],
            request_id=request_id,
            settings=self._settings,
            providers=self._providers,
            enabled=self._settings.hallucination_gate_enabled,
            judge_model=self._settings.hallucination_judge_model,
        )
        return RagEstimationOutcome(
            result=result,
            report=report,
            coherence_report=coherence_report,
            hallucination_report=hallucination_report,
            chunk_texts=[],
            model=None,
            provider=None,
            usage=None,
            finish_reason=None,
            prompt_version="estimation/rag/v1",
        )

    def _log_citation_report(self, report: CitationReport) -> None:
        logger.info(
            "citation_verification_completed",
            extra={
                "request_id": report.request_id,
                "grounded_ok": report.counts.get(CitationLineStatus.GROUNDED_OK, 0),
                "dangling": report.counts.get(CitationLineStatus.DANGLING_CITATION, 0),
                "insufficient": report.counts.get(CitationLineStatus.INSUFFICIENT_DATA, 0),
                "integrity_violations": report.counts.get(CitationLineStatus.INTEGRITY_VIOLATION, 0),
            },
        )
        for line in report.lines:
            if line.status != CitationLineStatus.DANGLING_CITATION:
                continue
            logger.warning(
                "citation_dangling_line",
                extra={
                    "request_id": report.request_id,
                    "component": line.component,
                    "invalid_chunk_ids": line.invalid_chunk_ids,
                },
            )
