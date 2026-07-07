"""Stateless RAG pipeline stage endpoints (feature-062)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session
from app.deps import get_request_id
from app.embedding_pipeline.advanced_retrieval import advanced_retrieve
from app.embedding_pipeline.chunk_content_repository import ChunkContent, ChunkContentRepository
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.lexical_search_repository import LexicalSearchRepository
from app.embedding_pipeline.rerank import Reranker, build_reranker
from app.embedding_pipeline.retrieval_schemas import RetrievalResultRow
from app.embedding_pipeline.retrieval_service import RetrievalService, parse_retrieval_mode
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.middleware.rate_limiting import conditional_rate_limit
from app.middleware.security import require_estimate_key
from app.routers.retrieval import get_effective_settings
from app.schemas.citation_report import CitationLineStatus
from app.schemas.estimation_query import compose_search_text
from app.schemas.rag_estimation_result import RagEstimationResult
from app.schemas.rag_stages import (
    AssembleStageRequest,
    AssembleStageResponse,
    GenerateStageRequest,
    GenerateStageResponse,
    ReformulateStageRequest,
    ReformulateStageResponse,
    RetrieveStageRequest,
    RetrieveStageResponse,
    StageChunkView,
    StructureStageRequest,
    StructureStageResponse,
    VerifyStageRequest,
    VerifyStageResponse,
    resolve_retrieve_advanced_config,
)
from app.services.citation_verification import verify_citations
from app.services.llm_chain import build_provider_chain
from app.services.rag_coherence import check_coherence
from app.services.rag_context_assembler import (
    AssembledContext,
    resolve_rag_context_encoding,
    truncate_assembled_context,
)
from app.services.rag_estimation_prompt_rendering import render_rag_estimation_prompt
from app.services.rag_hallucination_gate import gate_estimate
from app.services.rag_query_reformulator import reformulate_query
from app.services.rag_structure_generator import generate_structure
from app.services.structured_llm_client import StructuredCompletionError, complete_structured

router = APIRouter(tags=["rag-stages"])
logger = logging.getLogger(__name__)
_retrieval_service = RetrievalService()
_content_repository = ChunkContentRepository()


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


def _rows_to_stage_chunks(
    rows: list[RetrievalResultRow],
    contents: dict[int, ChunkContent],
    *,
    collection: str = "budgets",
) -> list[StageChunkView]:
    chunks: list[StageChunkView] = []
    for row in rows:
        content = contents.get(row.chunk_id)
        if content is None:
            continue
        chunks.append(
            StageChunkView(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                content=content.content,
                collection=collection,
                budget_id=content.budget_id,
                metadata=dict(content.metadata),
            )
        )
    return chunks


def _assembled_from_stage_chunks(chunks: list[StageChunkView]) -> AssembledContext:
    blocks: list[str] = []
    chunk_ids: set[int] = set()
    chunk_texts: list[str] = []
    for chunk in chunks:
        chunk_ids.add(chunk.chunk_id)
        chunk_texts.append(chunk.content)
        budget_line = f"budget_id: {chunk.budget_id}" if chunk.budget_id else "budget_id:"
        blocks.append(
            "\n".join(
                [
                    "[CHUNK START]",
                    f"chunk_id: {chunk.chunk_id}",
                    f"document_id: {chunk.document_id}",
                    budget_line,
                    "content:",
                    chunk.content,
                    "[CHUNK END]",
                ]
            )
        )
    return AssembledContext(
        prompt_block="\n\n".join(blocks),
        chunk_ids=chunk_ids,
        chunk_texts=chunk_texts,
    )


def _stage_chunks_from_assembled(
    assembled: AssembledContext,
    source_chunks: list[StageChunkView],
) -> list[StageChunkView]:
    by_id = {chunk.chunk_id: chunk for chunk in source_chunks}
    return [by_id[cid] for cid in sorted(assembled.chunk_ids) if cid in by_id]


@router.post(
    "/estimate/rag/stages/reformulate",
    response_model=ReformulateStageResponse,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("30/minute")
async def stage_reformulate(
    request: Request,
    payload: ReformulateStageRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReformulateStageResponse:
    request_id = get_request_id(request)
    try:
        query = await reformulate_query(
            payload.question,
            transcript=payload.transcript,
            settings=settings,
            providers=build_provider_chain(settings),
        )
        search_text = compose_search_text(query)
    except Exception as exc:
        logger.error(
            "rag_stage_failed",
            extra={"request_id": request_id, "stage": "reformulate", "error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Query reformulation failed.",
        ) from exc
    return ReformulateStageResponse(query=query, search_text=search_text)


@router.post(
    "/estimate/rag/stages/retrieve",
    response_model=RetrieveStageResponse,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("60/minute")
async def stage_retrieve(
    request: Request,
    payload: RetrieveStageRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_effective_settings)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
    vector_repository: Annotated[SemanticSearchRepository, Depends(get_vector_repository)],
    lexical_repository: Annotated[LexicalSearchRepository, Depends(get_lexical_repository)],
) -> RetrieveStageResponse:
    request_id = get_request_id(request)
    recall_k = payload.recall_k or settings.retrieval_recall_k
    top_k_final = payload.top_k_final or settings.retrieval_top_k_final

    try:
        if payload.use_advanced:
            stage_config = resolve_retrieve_advanced_config(payload)
            advanced = await advanced_retrieve(
                session,
                payload.search_text,
                stage_config,
                recall_k=recall_k,
                top_k_final=top_k_final,
                embedder=embedder,
                reranker=reranker,
                settings=settings,
                vector_repository=vector_repository,
                lexical_repository=lexical_repository,
            )
            rows = [
                RetrievalResultRow(
                    final_position=row.final_position,
                    chunk_id=row.chunk_id,
                    document_id=row.document_id,
                    budget_id=row.budget_id,
                    score=row.score,
                    vector_score=row.vector_score,
                    lexical_score=row.lexical_score,
                    fusion_score=row.fusion_score,
                    rerank_score=row.rerank_score,
                    matched_terms=row.matched_terms,
                    source_strategies=row.source_strategies,
                    metadata=row.metadata,
                )
                for row in advanced.results
            ]
            contents = await _content_repository.get_contents_by_ids(
                session,
                [row.chunk_id for row in rows],
            )
            chunks = _rows_to_stage_chunks(rows, contents, collection=advanced.results[0].collection if advanced.results else "budgets")
            return RetrieveStageResponse(chunks=chunks, advanced=True)

        mode = parse_retrieval_mode(payload.mode or settings.rag_estimation_retrieval_mode)
        retrieval = await _retrieval_service.retrieve(
            payload.search_text,
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
        contents = await _content_repository.get_contents_by_ids(
            session,
            [row.chunk_id for row in retrieval.results],
        )
        chunks = _rows_to_stage_chunks(retrieval.results, contents)
        return RetrieveStageResponse(chunks=chunks, mode=mode.value, advanced=False)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(
            "rag_stage_failed",
            extra={"request_id": request_id, "stage": "retrieve", "error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Retrieval failed.",
        ) from exc


@router.post(
    "/estimate/rag/stages/assemble",
    response_model=AssembleStageResponse,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("60/minute")
async def stage_assemble(
    request: Request,
    payload: AssembleStageRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssembleStageResponse:
    request_id = get_request_id(request)
    del request_id
    assembled = _assembled_from_stage_chunks(payload.chunks)
    max_tokens = payload.max_context_tokens or settings.rag_context_max_tokens
    truncated = truncate_assembled_context(
        assembled,
        max_tokens=max_tokens,
        encoding=resolve_rag_context_encoding(settings),
    )
    kept = _stage_chunks_from_assembled(truncated, payload.chunks)
    encoding = resolve_rag_context_encoding(settings)
    token_count = len(encoding.encode(truncated.prompt_block))
    return AssembleStageResponse(
        context_block=truncated.prompt_block,
        kept_chunks=kept,
        dropped_count=len(payload.chunks) - len(kept),
        token_count=token_count,
    )


@router.post(
    "/estimate/rag/stages/structure",
    response_model=StructureStageResponse,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("15/minute")
async def stage_structure(
    request: Request,
    payload: StructureStageRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> StructureStageResponse:
    request_id = get_request_id(request)
    try:
        structure, _usage, _finish = await generate_structure(
            payload.query,
            settings=settings,
            providers=build_provider_chain(settings),
        )
    except StructuredCompletionError as exc:
        logger.error(
            "rag_stage_failed",
            extra={"request_id": request_id, "stage": "structure", "error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Structure generation failed.",
        ) from exc
    return StructureStageResponse(structure=structure)


@router.post(
    "/estimate/rag/stages/generate",
    response_model=GenerateStageResponse,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("15/minute")
async def stage_generate(
    request: Request,
    payload: GenerateStageRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> GenerateStageResponse:
    request_id = get_request_id(request)
    providers = build_provider_chain(settings)
    from app.services.provider_routing import resolve_first_litellm_route

    route = resolve_first_litellm_route(providers)
    if route is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Structured generation is temporarily unavailable.",
        )

    question = (payload.question or compose_search_text(payload.query)).strip()
    rendered = render_rag_estimation_prompt(question=question, prompt_block=payload.context_block)
    try:
        estimate, _usage, _finish = await complete_structured(
            litellm_model=route.litellm_model,
            chain_provider=route.provider_name,
            api_key=route.api_key,
            timeout_seconds=route.timeout_seconds,
            system_prompt=rendered.system_prompt,
            user_prompt=rendered.user_prompt,
            max_output_tokens=settings.estimation_output_tokens_max,
            response_model=RagEstimationResult,
            max_attempts=settings.structured_output_max_attempts,
        )
    except StructuredCompletionError as exc:
        logger.error(
            "rag_stage_failed",
            extra={"request_id": request_id, "stage": "generate", "error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Estimate generation failed.",
        ) from exc

    chunk_ids = {chunk.chunk_id for chunk in payload.kept_chunks}
    report = verify_citations(estimate, chunk_ids, request_id=request_id)
    coherence_report = check_coherence(
        estimate,
        request_id=request_id,
        enabled=settings.rag_coherence_enabled,
        total_tolerance=settings.rag_coherence_total_tolerance,
    )
    fabricated: list[int] = []
    for line in report.lines:
        if line.status == CitationLineStatus.DANGLING_CITATION:
            fabricated.extend(line.invalid_chunk_ids)
    return GenerateStageResponse(
        estimate=estimate,
        fabricated_source_ids=fabricated,
        coherent=not coherence_report.has_violations,
        citation_report=report,
        coherence_report=coherence_report,
    )


@router.post(
    "/estimate/rag/stages/verify",
    response_model=VerifyStageResponse,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("15/minute")
async def stage_verify(
    request: Request,
    payload: VerifyStageRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> VerifyStageResponse:
    request_id = get_request_id(request)
    chunk_ids = {chunk.chunk_id for chunk in payload.kept_chunks}
    citation_report = verify_citations(payload.estimate, chunk_ids, request_id=request_id)
    coherence_report = check_coherence(
        payload.estimate,
        request_id=request_id,
        enabled=settings.rag_coherence_enabled,
        total_tolerance=settings.rag_coherence_total_tolerance,
    )
    use_judge = (
        payload.use_judge
        if payload.use_judge is not None
        else settings.hallucination_gate_enabled
    )
    hallucination_report = await gate_estimate(
        payload.estimate,
        chunk_texts=[chunk.content for chunk in payload.kept_chunks],
        request_id=request_id,
        settings=settings,
        providers=build_provider_chain(settings),
        enabled=use_judge,
        judge_model=settings.hallucination_judge_model,
    )
    return VerifyStageResponse(
        citation_report=citation_report,
        coherence_report=coherence_report,
        hallucination_report=hallucination_report,
    )
