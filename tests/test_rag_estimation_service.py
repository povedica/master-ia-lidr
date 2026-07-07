"""Unit tests for RagEstimationService orchestration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.embedding_pipeline.chunk_content_repository import ChunkContent, ChunkContentRepository
from app.embedding_pipeline.retrieval_schemas import (
    RetrievalAppliedConfig,
    RetrievalResponse,
    RetrievalResultRow,
    RetrievalRerankConfig,
    RetrievalTimingsMs,
)
from app.embedding_pipeline.retrieval_service import RetrievalMode, RetrievalService
from app.schemas.citation_report import CitationLineStatus
from app.schemas.coherence_report import CoherenceLineStatus
from app.schemas.estimation_query import EstimationQuery
from app.schemas.hallucination_report import HallucinationLineGrade, HallucinationReport
from app.schemas.rag_estimation_result import RagEstimationLineItem, RagEstimationResult, SourceReference
from app.services.llm_chain import LitellmChainProvider
from app.services.llm_types import UsageInfo
from app.services.rag_estimation_service import RagEstimationService


def _noop_hallucination_report(request_id: str = "req_test") -> HallucinationReport:
    return HallucinationReport(
        request_id=request_id,
        lines=[],
        counts={grade: 0 for grade in HallucinationLineGrade},
        has_degraded=False,
    )


def _retrieval_response(*chunk_ids: int) -> RetrievalResponse:
    return RetrievalResponse(
        query="test",
        mode="B",
        applied_config=RetrievalAppliedConfig(
            mode="B",
            recall_k=50,
            top_k_final=5,
            branches=["vector", "lexical"],
            rerank=RetrievalRerankConfig(enabled=False, model="", is_noop=True),
            text_search_config="spanish",
        ),
        timings_ms=RetrievalTimingsMs(total=10),
        results=[
            RetrievalResultRow(
                final_position=index + 1,
                chunk_id=chunk_id,
                document_id=7,
                budget_id="BUD-2024-014",
                score=0.9,
                metadata={"budget_id": "BUD-2024-014"},
            )
            for index, chunk_id in enumerate(chunk_ids)
        ],
    )


def _service(
    *,
    retrieval: RetrievalService | None = None,
    content_repository: ChunkContentRepository | None = None,
) -> RagEstimationService:
    settings = Settings(_env_file=None)
    providers = [
        LitellmChainProvider(
            name="openai",
            litellm_model="gpt-4o-mini",
            api_key="test-key",
            timeout_seconds=30.0,
        )
    ]
    return RagEstimationService(
        settings=settings,
        retrieval_service=retrieval or AsyncMock(spec=RetrievalService),
        content_repository=content_repository or ChunkContentRepository(),
        providers=providers,
    )


@pytest.mark.asyncio
async def test_insufficient_context_when_retrieval_returns_no_rows() -> None:
    retrieval = AsyncMock(spec=RetrievalService)
    retrieval.retrieve = AsyncMock(return_value=_retrieval_response())
    retrieval.retrieve.return_value = RetrievalResponse(
        query="test",
        mode="B",
        applied_config=_retrieval_response().applied_config,
        timings_ms=RetrievalTimingsMs(total=1),
        results=[],
    )
    service = _service(retrieval=retrieval)

    outcome = await service.estimate(
        "OAuth platform",
        request_id="req_insufficient",
        session=AsyncMock(),
        embedder=AsyncMock(),
        reranker=AsyncMock(),
        mode=RetrievalMode.B,
        recall_k=50,
        top_k_final=5,
    )

    assert outcome.result.insufficient_context is True
    assert outcome.result.line_items == []
    assert outcome.chunk_texts == []
    assert outcome.coherence_report.has_violations is False
    assert outcome.coherence_report.lines == []
    assert outcome.hallucination_report.has_degraded is False
    assert outcome.hallucination_report.lines == []


@pytest.mark.asyncio
async def test_happy_path_generates_and_verifies_citations() -> None:
    retrieval = AsyncMock(spec=RetrievalService)
    retrieval.retrieve = AsyncMock(return_value=_retrieval_response(42))
    content_repository = AsyncMock(spec=ChunkContentRepository)
    content_repository.get_contents_by_ids = AsyncMock(
        return_value={
            42: ChunkContent(
                chunk_id=42,
                document_id=7,
                budget_id="BUD-2024-014",
                content="OAuth2 login integration scope",
                metadata={"budget_id": "BUD-2024-014"},
            )
        }
    )
    llm_result = RagEstimationResult(
        summary="Grounded estimate for OAuth integration from retrieved budget chunk.",
        line_items=[
            RagEstimationLineItem(
                component="authentication",
                hours=12.0,
                rationale="OAuth2 scope from retrieved chunk.",
                grounded=True,
                sources=[
                    SourceReference(
                        chunk_id=42,
                        document_id=7,
                        budget_id="BUD-2024-014",
                        evidence="OAuth2 login integration scope",
                    )
                ],
            )
        ],
        total_hours=12.0,
        insufficient_context=False,
    )
    service = _service(retrieval=retrieval, content_repository=content_repository)

    with patch(
        "app.services.rag_estimation_service.complete_structured",
        new=AsyncMock(return_value=(llm_result, UsageInfo(prompt_tokens=1, completion_tokens=2, total_tokens=3), "stop")),
    ):
        outcome = await service.estimate(
            "OAuth platform",
            request_id="req_ok",
            session=AsyncMock(),
            embedder=AsyncMock(),
            reranker=AsyncMock(),
            mode=RetrievalMode.B,
            recall_k=50,
            top_k_final=5,
        )

    assert outcome.result.line_items[0].grounded is True
    assert outcome.report.lines[0].status == CitationLineStatus.GROUNDED_OK
    assert outcome.coherence_report.has_violations is False
    assert outcome.coherence_report.lines[0].status == CoherenceLineStatus.COHERENT_OK
    assert outcome.chunk_texts == ["OAuth2 login integration scope"]
    assert outcome.provider == "openai"
    assert outcome.hallucination_report.has_degraded is False


@pytest.mark.asyncio
async def test_hallucination_gate_disabled_skips_judge_llm() -> None:
    retrieval = AsyncMock(spec=RetrievalService)
    retrieval.retrieve = AsyncMock(return_value=_retrieval_response(42))
    content_repository = AsyncMock(spec=ChunkContentRepository)
    content_repository.get_contents_by_ids = AsyncMock(
        return_value={
            42: ChunkContent(
                chunk_id=42,
                document_id=7,
                budget_id="BUD-2024-014",
                content="OAuth2 login integration scope — prior budget line: 8 hours.",
                metadata={"budget_id": "BUD-2024-014"},
            )
        }
    )
    llm_result = RagEstimationResult(
        summary="Grounded estimate for OAuth integration from retrieved budget chunk.",
        line_items=[
            RagEstimationLineItem(
                component="authentication",
                hours=80.0,
                rationale="Inflated hours line for hallucination gate test.",
                grounded=True,
                sources=[
                    SourceReference(
                        chunk_id=42,
                        document_id=7,
                        budget_id="BUD-2024-014",
                        evidence="OAuth2 login integration scope",
                    )
                ],
            )
        ],
        total_hours=80.0,
        insufficient_context=False,
    )
    settings = Settings(_env_file=None, hallucination_gate_enabled=False)
    service = RagEstimationService(
        settings=settings,
        retrieval_service=retrieval,
        content_repository=content_repository,
        providers=[
            LitellmChainProvider(
                name="openai",
                litellm_model="gpt-4o-mini",
                api_key="test-key",
                timeout_seconds=30.0,
            )
        ],
    )

    with (
        patch(
            "app.services.rag_estimation_service.complete_structured",
            new=AsyncMock(return_value=(llm_result, None, "stop")),
        ),
        patch(
            "app.services.rag_hallucination_gate.judge_estimate",
            new=AsyncMock(),
        ) as mock_judge,
    ):
        outcome = await service.estimate(
            "OAuth platform",
            request_id="req_gate_off",
            session=AsyncMock(),
            embedder=AsyncMock(),
            reranker=AsyncMock(),
            mode=RetrievalMode.B,
            recall_k=50,
            top_k_final=5,
        )

    mock_judge.assert_not_awaited()
    assert outcome.hallucination_report.has_degraded is False
    assert outcome.hallucination_report.lines == []


@pytest.mark.asyncio
async def test_hallucination_gate_enabled_marks_inflated_hours_degraded() -> None:
    from app.schemas.hallucination_report import HallucinationJudgeLineResult

    retrieval = AsyncMock(spec=RetrievalService)
    retrieval.retrieve = AsyncMock(return_value=_retrieval_response(42))
    content_repository = AsyncMock(spec=ChunkContentRepository)
    content_repository.get_contents_by_ids = AsyncMock(
        return_value={
            42: ChunkContent(
                chunk_id=42,
                document_id=7,
                budget_id="BUD-2024-014",
                content="OAuth2 login integration scope — prior budget line: 8 hours.",
                metadata={"budget_id": "BUD-2024-014"},
            )
        }
    )
    llm_result = RagEstimationResult(
        summary="Grounded estimate for OAuth integration from retrieved budget chunk.",
        line_items=[
            RagEstimationLineItem(
                component="authentication",
                hours=80.0,
                rationale="Inflated hours line for hallucination gate test.",
                grounded=True,
                sources=[
                    SourceReference(
                        chunk_id=42,
                        document_id=7,
                        budget_id="BUD-2024-014",
                        evidence="OAuth2 login integration scope",
                    )
                ],
            )
        ],
        total_hours=80.0,
        insufficient_context=False,
    )
    settings = Settings(_env_file=None, hallucination_gate_enabled=True)
    service = RagEstimationService(
        settings=settings,
        retrieval_service=retrieval,
        content_repository=content_repository,
        providers=[
            LitellmChainProvider(
                name="openai",
                litellm_model="gpt-4o-mini",
                api_key="test-key",
                timeout_seconds=30.0,
            )
        ],
    )

    with (
        patch(
            "app.services.rag_estimation_service.complete_structured",
            new=AsyncMock(return_value=(llm_result, None, "stop")),
        ),
        patch(
            "app.services.rag_hallucination_gate.judge_estimate",
            new=AsyncMock(
                return_value=[
                    HallucinationJudgeLineResult(
                        index=0,
                        grade=HallucinationLineGrade.GROUNDED,
                    )
                ]
            ),
        ) as mock_judge,
    ):
        outcome = await service.estimate(
            "OAuth platform",
            request_id="req_gate_on",
            session=AsyncMock(),
            embedder=AsyncMock(),
            reranker=AsyncMock(),
            mode=RetrievalMode.B,
            recall_k=50,
            top_k_final=5,
        )

    mock_judge.assert_awaited_once()
    assert outcome.hallucination_report.has_degraded is True
    assert outcome.hallucination_report.lines[0].grade == HallucinationLineGrade.DEGRADED


@pytest.mark.asyncio
async def test_retrieval_uses_composed_search_text_from_reformulator() -> None:
    retrieval = AsyncMock(spec=RetrievalService)
    retrieval.retrieve = AsyncMock(return_value=_retrieval_response())
    service = _service(retrieval=retrieval)
    reformulated = EstimationQuery(
        question="OAuth platform",
        search_facets=["OAuth2", "SSO"],
        component_hints=["authentication"],
        sector_filters=[],
    )

    with patch(
        "app.services.rag_estimation_service.reformulate_query",
        new=AsyncMock(return_value=reformulated),
    ):
        await service.estimate(
            "OAuth platform",
            transcript="Need SSO for CRM",
            request_id="req_search_text",
            session=AsyncMock(),
            embedder=AsyncMock(),
            reranker=AsyncMock(),
            mode=RetrievalMode.B,
            recall_k=50,
            top_k_final=5,
        )

    retrieval.retrieve.assert_awaited_once()
    search_text = retrieval.retrieve.await_args.args[0]
    assert search_text == (
        "OAuth platform | facets: OAuth2, SSO | components: authentication"
    )


@pytest.mark.asyncio
async def test_truncates_assembled_context_before_generation() -> None:
    retrieval = AsyncMock(spec=RetrievalService)
    retrieval.retrieve = AsyncMock(return_value=_retrieval_response(42, 43))
    content_repository = AsyncMock(spec=ChunkContentRepository)
    content_repository.get_contents_by_ids = AsyncMock(
        return_value={
            42: ChunkContent(
                chunk_id=42,
                document_id=7,
                budget_id="BUD-2024-014",
                content="OAuth2 scope",
                metadata={"budget_id": "BUD-2024-014"},
            ),
            43: ChunkContent(
                chunk_id=43,
                document_id=8,
                budget_id="BUD-2024-032",
                content="Stripe checkout integration " * 80,
                metadata={"budget_id": "BUD-2024-032"},
            ),
        }
    )
    llm_result = RagEstimationResult(
        summary="Grounded estimate with truncated retrieval context for prompt rendering.",
        line_items=[],
        total_hours=0.0,
        insufficient_context=True,
    )
    settings = Settings(_env_file=None, rag_context_max_tokens=120)
    service = RagEstimationService(
        settings=settings,
        retrieval_service=retrieval,
        content_repository=content_repository,
        providers=[
            LitellmChainProvider(
                name="openai",
                litellm_model="gpt-4o-mini",
                api_key="test-key",
                timeout_seconds=30.0,
            )
        ],
    )

    with patch(
        "app.services.rag_estimation_service.complete_structured",
        new=AsyncMock(return_value=(llm_result, None, "stop")),
    ) as mock_complete:
        outcome = await service.estimate(
            "OAuth platform",
            request_id="req_truncate",
            session=AsyncMock(),
            embedder=AsyncMock(),
            reranker=AsyncMock(),
            mode=RetrievalMode.B,
            recall_k=50,
            top_k_final=5,
        )

    user_prompt = mock_complete.await_args.kwargs["user_prompt"]
    assert "chunk_id: 43" not in user_prompt
    assert len(outcome.chunk_texts) == 1

