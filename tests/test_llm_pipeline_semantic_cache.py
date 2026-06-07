"""Semantic cache integration on ``LLMPipeline`` (in-memory store, fake embeddings)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.guardrails.llm_pipeline import LLMPipeline
from app.schemas.estimation_request import EstimationRequest
from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from app.services.estimation_request_render import render_estimation_assessment_surface
from app.services.llm_service import StructuredEstimateBundle, StructuredPrelude, UsageInfo
from app.services.semantic_cache.embeddings import FakeEmbeddingProvider
from app.services.semantic_cache.repository import InMemorySemanticCacheRepository
from app.services.semantic_cache.service import SemanticCacheService
from tests.estimation_fixtures import minimal_estimation_request_dict


class _StubWithPrelude:
    def __init__(self) -> None:
        self.calls = 0

    async def prepare_structured_prelude(
        self,
        request: EstimationRequest,
        *,
        assessment_surface: str,
        skip_domain_guardrail: bool = False,
    ) -> StructuredPrelude:
        del request, assessment_surface, skip_domain_guardrail
        return StructuredPrelude(
            preprocessed_markdown_for_template=None,
            phase1_prep_in=0,
            phase1_prep_out=0,
            max_output_tokens=2048,
        )

    async def estimate_structured(
        self,
        request: EstimationRequest,
        *,
        assessment_surface: str,
        skip_domain_guardrail: bool = False,
        system_prompt_override: str | None = None,
        user_prompt_override: str | None = None,
        messages_override: list[dict[str, str]] | None = None,
    ) -> StructuredEstimateBundle:
        self.calls += 1
        assert skip_domain_guardrail is True
        del request, assessment_surface
        li = EstimationLineItem(name="Task", hours=1.0, cost_eur=10.0)
        totals = EstimationTotals(hours=1.0, cost_eur=10.0)
        result = EstimationResult(
            title="Semantic cache pipeline test",
            summary="Structured summary with enough length for validators.",
            phases=[],
            line_items=[li],
            totals=totals,
            duration_weeks=2.0,
            confidence=0.8,
        )
        return StructuredEstimateBundle(
            result=result,
            prompt_version="stub/prompt",
            examples_version="stub/ex",
            model="stub-model",
            provider="stub",
            usage=UsageInfo(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            degraded=False,
            finish_reason="stop",
        )


@pytest.mark.asyncio
async def test_second_identical_request_uses_semantic_cache_hit() -> None:
    settings = Settings(
        openai_api_key="x",
        llm_domain_guardrail_enabled=True,
        guardrail_rollout_prompt_injection_patterns="disabled",
        guardrail_rollout_pii_basic="disabled",
        semantic_cache_enabled=True,
        semantic_cache_log_only=False,
        semantic_cache_use_memory_store=True,
        semantic_cache_similarity_threshold=0.5,
    )
    stub = _StubWithPrelude()
    cache = SemanticCacheService(
        settings=settings,
        repository=InMemorySemanticCacheRepository(),
        embedder=FakeEmbeddingProvider(),
    )
    pipeline = LLMPipeline(stub, settings, semantic_cache=cache)  # type: ignore[arg-type]
    body = EstimationRequest.model_validate(minimal_estimation_request_dict(evaluate=False))
    surface = render_estimation_assessment_surface(body)

    first = await pipeline.run_structured(body, assessment_surface=surface, request_id="req_sem_1")
    assert first.cached is False
    assert stub.calls == 1

    second = await pipeline.run_structured(body, assessment_surface=surface, request_id="req_sem_2")
    assert second.cached is True
    assert stub.calls == 1
    assert second.cache_score is not None
    assert second.cache_bucket is not None
