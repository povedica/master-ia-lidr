"""Guarded structured estimation pipeline (v2 orchestration)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.config import Settings
from app.guardrails.audit import new_audit_id
from app.guardrails.acb.context import AcbRunContext
from app.guardrails.acb.orchestrator import ActorCriticBossOrchestrator
from app.guardrails.contracts import (
    FinalResponseStatus,
    GuardrailPolicy,
    GuardrailResult,
    PolicyOutcome,
    PolicyOutcomeStatus,
)
from app.guardrails.fallback_estimation import build_degraded_estimation_result
from app.guardrails.input_semantic import run_input_semantic_phase
from app.guardrails.output_semantic import evaluate_output_semantic_guardrails
from app.guardrails.pipeline_context import CacheMetadata, PipelineContext, RenderedPromptRef
from app.guardrails.policy_executor import PolicyExecutor
from app.guardrails.policy_registry import guardrail_declaration_by_id
from app.schemas.estimation_request import EstimationRequest
from app.schemas.acb.trace import AcbTrace
from app.services.estimation_prompt_rendering import render_guided_user_message
from app.services.llm_service import (
    EXAMPLES_VERSION,
    EstimationError,
    EstimationService,
    StructuredEstimateBundle,
)
from app.services.prompt_versions import resolve_prompt_bundle_version, resolve_prompt_template_set
from app.services.semantic_cache.bucket import (
    build_semantic_cache_bucket,
    build_vector_text_surface,
    input_fingerprint_for_vector_text,
)
from app.services.semantic_cache.contracts import (
    CachedEstimationArtifact,
    CacheDecisionStatus,
    SemanticCacheLookupRequest,
)
from app.services.semantic_cache.factory import build_semantic_cache_service
from app.services.semantic_cache.artifacts import structured_bundle_to_artifact_fields
from app.services.semantic_cache.service import SemanticCacheService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StructuredPipelineOutcome:
    """End state for a guarded structured estimation run."""

    bundle: StructuredEstimateBundle | None
    final_status: FinalResponseStatus
    reason_code: str | None
    user_message: str | None
    technical_message: str | None
    audit_id: str
    safe_to_cache: bool
    safe_to_display: bool
    input_guardrail_results: tuple[GuardrailResult, ...] = ()
    output_guardrail_results: tuple[GuardrailResult, ...] = ()
    policy_outcomes: tuple[PolicyOutcome, ...] = ()
    cached: bool = False
    cache_score: float | None = None
    cache_bucket: str | None = None
    cache_miss_reason: str | None = None
    acb_trace: AcbTrace | None = None


class LLMPipeline:
    """Coordinates input guardrails, provider call, and output semantic validation."""

    def __init__(
        self,
        service: EstimationService,
        settings: Settings,
        *,
        semantic_cache: SemanticCacheService | None = None,
    ) -> None:
        self._service = service
        self._settings = settings
        self._semantic_cache = semantic_cache if semantic_cache is not None else build_semantic_cache_service(settings)

    async def run_structured(
        self,
        request: EstimationRequest,
        *,
        assessment_surface: str,
        request_id: str,
        guided_user_message: str | None = None,
        system_prompt_override: str | None = None,
        user_prompt_override: str | None = None,
        messages_override: list[dict[str, str]] | None = None,
    ) -> StructuredPipelineOutcome:
        """Execute the guarded v2 path (raises ``GuardrailViolationError`` on enforced blocks)."""

        audit_id = new_audit_id()
        started = perf_counter()
        guided = (
            guided_user_message.strip()
            if guided_user_message is not None
            else render_guided_user_message(request, settings=self._settings).strip()
        )
        if not guided:
            return StructuredPipelineOutcome(
                bundle=None,
                final_status=FinalResponseStatus.ERROR,
                reason_code="invalid_request",
                user_message="Request payload is empty after rendering.",
                technical_message="guided_user_message_empty",
                audit_id=audit_id,
                safe_to_cache=False,
                safe_to_display=False,
            )

        surface = assessment_surface.strip() or guided
        rules_version = self._settings.guardrail_rules_version.strip() or "registry-default"
        ctx = PipelineContext(
            request_id=request_id,
            audit_id=audit_id,
            estimation_request=request,
            user_input=guided,
            assessment_surface=surface,
            guardrail_rules_version=rules_version,
            cache_metadata=CacheMetadata(looked_up=False, hit=False, safe_to_cache=False),
        )

        input_phase = await run_input_semantic_phase(
            assessment_surface=assessment_surface,
            guided_user_message=guided,
            settings=self._settings,
            audit_id=audit_id,
        )
        ctx.validation_results.extend(input_phase.results)
        ctx.timings_ms["input_semantic_ms"] = int((perf_counter() - started) * 1000)

        policy_parts: list[PolicyOutcome] = list(input_phase.outcomes)
        if input_phase.degraded:
            degraded_result = build_degraded_estimation_result(
                user_summary=input_phase.degrade_user_message or "Unable to complete this estimation.",
            )
            bundle = StructuredEstimateBundle(
                result=degraded_result,
                prompt_version="guardrail/degraded",
                examples_version="guardrail/degraded",
                model="guardrail",
                provider="guardrail",
                usage=None,
                degraded=True,
                finish_reason="guardrail_filter",
            )
            combined_policies = tuple(policy_parts)
            return StructuredPipelineOutcome(
                bundle=bundle,
                final_status=FinalResponseStatus.DEGRADED,
                reason_code=input_phase.degrade_reason_code,
                user_message=input_phase.degrade_user_message,
                technical_message=None,
                audit_id=audit_id,
                safe_to_cache=False,
                safe_to_display=True,
                input_guardrail_results=input_phase.results,
                output_guardrail_results=(),
                policy_outcomes=combined_policies,
            )

        semantic_lookup: SemanticCacheLookupRequest | None = None
        cache_embedding: list[float] | None = None
        vector_text_cache = ""
        cache_score_out: float | None = None
        cache_bucket_out: str | None = None
        cache_miss_out: str | None = None

        if self._semantic_cache is not None and hasattr(self._service, "prepare_structured_prelude"):
            prelude = await self._service.prepare_structured_prelude(
                request,
                assessment_surface=assessment_surface,
                skip_domain_guardrail=True,
            )
            bundle_version = resolve_prompt_bundle_version(self._settings)
            template_set = resolve_prompt_template_set("estimation", bundle_version)
            prompt_version = f"{template_set.use_case}/{template_set.version}"
            examples_version = EXAMPLES_VERSION
            bucket = build_semantic_cache_bucket(
                request=request,
                settings=self._settings,
                prompt_version=prompt_version,
                examples_version=examples_version,
                output_schema_version="1",
                guardrail_rules_version=rules_version,
                operation="estimation_v2",
                tenant_id="default",
            )
            vector_text_cache = build_vector_text_surface(
                request=request,
                assessment_surface=assessment_surface,
            )
            lookup = SemanticCacheLookupRequest(
                operation="estimation_v2",
                endpoint="api_v2_estimate",
                tenant_id="default",
                bucket=bucket,
                vector_text=vector_text_cache,
                request_id=request_id,
            )
            semantic_lookup = lookup
            cache_result, cache_embedding = await self._semantic_cache.evaluate_lookup(lookup)
            if ctx.cache_metadata is not None:
                ctx.cache_metadata.looked_up = True
            cache_score_out = cache_result.top_score
            cache_bucket_out = bucket.display_key
            if cache_result.miss_reason is not None:
                cache_miss_out = cache_result.miss_reason.value
            if cache_result.status == CacheDecisionStatus.hit:
                hit_bundle = self._semantic_cache.bundle_from_hit(cache_result)
                if hit_bundle is not None:
                    if ctx.cache_metadata is not None:
                        ctx.cache_metadata.hit = True
                        ctx.cache_metadata.safe_to_cache = True
                    ctx.prompt_version = hit_bundle.prompt_version
                    ctx.output_schema_version = hit_bundle.result.schema_version
                    ctx.rendered_prompt = RenderedPromptRef(
                        prompt_version=hit_bundle.prompt_version,
                        examples_version=hit_bundle.examples_version,
                    )
                    return StructuredPipelineOutcome(
                        bundle=hit_bundle,
                        final_status=FinalResponseStatus.SUCCESS,
                        reason_code=None,
                        user_message=None,
                        technical_message=None,
                        audit_id=audit_id,
                        safe_to_cache=True,
                        safe_to_display=True,
                        input_guardrail_results=input_phase.results,
                        output_guardrail_results=(),
                        policy_outcomes=tuple(policy_parts),
                        cached=True,
                        cache_score=cache_score_out,
                        cache_bucket=cache_bucket_out,
                        cache_miss_reason=None,
                    )

        try:
            bundle = await self._service.estimate_structured(
                request,
                assessment_surface=assessment_surface,
                skip_domain_guardrail=True,
                system_prompt_override=system_prompt_override,
                user_prompt_override=user_prompt_override,
                messages_override=messages_override,
            )
        except EstimationError as exc:
            return StructuredPipelineOutcome(
                bundle=None,
                final_status=FinalResponseStatus.ERROR,
                reason_code="estimation_failed",
                user_message=str(exc).strip() or "Unable to complete structured estimation.",
                technical_message=type(exc).__name__,
                audit_id=audit_id,
                safe_to_cache=False,
                safe_to_display=False,
                input_guardrail_results=input_phase.results,
                policy_outcomes=tuple(policy_parts),
                cache_score=cache_score_out,
                cache_bucket=cache_bucket_out,
                cache_miss_reason=cache_miss_out,
            )

        ctx.prompt_version = bundle.prompt_version
        ctx.output_schema_version = bundle.result.schema_version
        ctx.rendered_prompt = RenderedPromptRef(
            prompt_version=bundle.prompt_version,
            examples_version=bundle.examples_version,
        )

        out_started = perf_counter()
        out_results = evaluate_output_semantic_guardrails(
            request=request,
            result=bundle.result,
            settings=self._settings,
        )
        executor = PolicyExecutor(self._settings)
        out_policies: list[PolicyOutcome] = []
        final_bundle = bundle
        output_degraded = False
        degrade_reason: str | None = None
        degrade_message: str | None = None

        for res in out_results:
            po = executor.apply(res, audit_id=audit_id)
            out_policies.append(po)
            if res.passed or po.status != PolicyOutcomeStatus.ENFORCED:
                continue
            decl = guardrail_declaration_by_id(res.guardrail_id)
            if decl is None:
                continue
            if decl.on_fail == GuardrailPolicy.FILTER:
                output_degraded = True
                degrade_reason = {
                    "output_confidence_floor": "low_confidence",
                    "output_sensitive_leakage": "unsafe_output",
                    "output_useless_placeholder": "semantic_mismatch",
                }.get(res.guardrail_id, "unsafe_output")
                degrade_message = "The model output did not pass semantic safety checks."
                final_bundle = StructuredEstimateBundle(
                    result=build_degraded_estimation_result(user_summary=degrade_message),
                    prompt_version=bundle.prompt_version,
                    examples_version=bundle.examples_version,
                    model=bundle.model,
                    provider=bundle.provider,
                    usage=bundle.usage,
                    degraded=True,
                    finish_reason="output_guardrail_filter",
                )
                break

        ctx.validation_results.extend(out_results)
        ctx.timings_ms["output_semantic_ms"] = int((perf_counter() - out_started) * 1000)
        policy_parts.extend(out_policies)

        if output_degraded:
            if ctx.cache_metadata is not None:
                ctx.cache_metadata.safe_to_cache = False
            return StructuredPipelineOutcome(
                bundle=final_bundle,
                final_status=FinalResponseStatus.DEGRADED,
                reason_code=degrade_reason,
                user_message=degrade_message,
                technical_message=None,
                audit_id=audit_id,
                safe_to_cache=False,
                safe_to_display=True,
                input_guardrail_results=input_phase.results,
                output_guardrail_results=tuple(out_results),
                policy_outcomes=tuple(policy_parts),
                cache_score=cache_score_out,
                cache_bucket=cache_bucket_out,
                cache_miss_reason=cache_miss_out,
            )

        if ctx.cache_metadata is not None:
            ctx.cache_metadata.safe_to_cache = True

        if self._semantic_cache is not None and semantic_lookup is not None:
            write_vector = cache_embedding
            if write_vector is None and vector_text_cache.strip():
                try:
                    write_vector = await self._semantic_cache.embed_for_request(vector_text_cache)
                except Exception:
                    write_vector = None
            if write_vector is not None:
                fields = structured_bundle_to_artifact_fields(final_bundle)
                artifact = CachedEstimationArtifact(
                    cache_schema_version=self._settings.semantic_cache_cache_schema_version,
                    bucket_hash=semantic_lookup.bucket.bucket_hash,
                    input_fingerprint=input_fingerprint_for_vector_text(vector_text_cache),
                    embedding_model=self._settings.semantic_cache_embedding_model,
                    embedding_model_version=self._settings.semantic_cache_embedding_model_version,
                    prompt_version=final_bundle.prompt_version,
                    examples_version=final_bundle.examples_version,
                    output_schema_version=final_bundle.result.schema_version,
                    guardrail_rules_version=rules_version,
                    provider=final_bundle.provider,
                    model=final_bundle.model,
                    result=fields["result"],
                    usage=fields["usage"],
                    finish_reason=fields.get("finish_reason"),
                    safe_to_cache=True,
                    safe_to_display=True,
                    degraded=bool(fields.get("degraded", False)),
                )
                await self._semantic_cache.maybe_write_validated(
                    lookup=semantic_lookup,
                    embedding=write_vector,
                    artifact=artifact,
                    safe_to_cache=True,
                    safe_to_display=True,
                    success=True,
                )

        return StructuredPipelineOutcome(
            bundle=final_bundle,
            final_status=FinalResponseStatus.SUCCESS,
            reason_code=None,
            user_message=None,
            technical_message=None,
            audit_id=audit_id,
            safe_to_cache=True,
            safe_to_display=True,
            input_guardrail_results=input_phase.results,
            output_guardrail_results=tuple(out_results),
            policy_outcomes=tuple(policy_parts),
            cached=False,
            cache_score=cache_score_out,
            cache_bucket=cache_bucket_out,
            cache_miss_reason=cache_miss_out,
        )

    async def run_structured_with_acb(
        self,
        request: EstimationRequest,
        *,
        assessment_surface: str,
        request_id: str,
        project_metadata: dict[str, Any],
        guided_user_message: str | None = None,
        system_prompt_override: str | None = None,
        user_prompt_override: str | None = None,
        messages_override: list[dict[str, str]] | None = None,
    ) -> StructuredPipelineOutcome:
        """Guarded structured path using Actor-Critic-Boss orchestration."""

        audit_id = new_audit_id()
        started = perf_counter()
        guided = (
            guided_user_message.strip()
            if guided_user_message is not None
            else render_guided_user_message(request, settings=self._settings).strip()
        )
        if not guided:
            return StructuredPipelineOutcome(
                bundle=None,
                final_status=FinalResponseStatus.ERROR,
                reason_code="invalid_request",
                user_message="Request payload is empty after rendering.",
                technical_message="guided_user_message_empty",
                audit_id=audit_id,
                safe_to_cache=False,
                safe_to_display=False,
            )

        surface = assessment_surface.strip() or guided
        rules_version = self._settings.guardrail_rules_version.strip() or "registry-default"
        ctx = PipelineContext(
            request_id=request_id,
            audit_id=audit_id,
            estimation_request=request,
            user_input=guided,
            assessment_surface=surface,
            guardrail_rules_version=rules_version,
            cache_metadata=CacheMetadata(looked_up=False, hit=False, safe_to_cache=False),
        )

        input_phase = await run_input_semantic_phase(
            assessment_surface=assessment_surface,
            guided_user_message=guided,
            settings=self._settings,
            audit_id=audit_id,
        )
        ctx.validation_results.extend(input_phase.results)
        ctx.timings_ms["input_semantic_ms"] = int((perf_counter() - started) * 1000)
        policy_parts: list[PolicyOutcome] = list(input_phase.outcomes)

        if input_phase.degraded:
            degraded_result = build_degraded_estimation_result(
                user_summary=input_phase.degrade_user_message or "Unable to complete this estimation.",
            )
            bundle = StructuredEstimateBundle(
                result=degraded_result,
                prompt_version="guardrail/degraded",
                examples_version="guardrail/degraded",
                model="guardrail",
                provider="guardrail",
                usage=None,
                degraded=True,
                finish_reason="guardrail_filter",
            )
            return StructuredPipelineOutcome(
                bundle=bundle,
                final_status=FinalResponseStatus.DEGRADED,
                reason_code=input_phase.degrade_reason_code,
                user_message=input_phase.degrade_user_message,
                technical_message=None,
                audit_id=audit_id,
                safe_to_cache=False,
                safe_to_display=True,
                input_guardrail_results=input_phase.results,
                output_guardrail_results=(),
                policy_outcomes=tuple(policy_parts),
            )

        if self._semantic_cache is not None and self._settings.semantic_cache_feature_active():
            logger.info(
                "acb_cache_bypassed",
                extra={"request_id": request_id, "endpoint": "session_estimate"},
            )

        acb_ctx = AcbRunContext(
            request=request,
            assessment_surface=surface,
            project_metadata=project_metadata,
            system_prompt_override=system_prompt_override,
            user_prompt_override=user_prompt_override,
            messages_override=messages_override,
            skip_domain_guardrail=True,
        )
        orchestrator = ActorCriticBossOrchestrator(self._service, self._settings)
        try:
            acb_outcome = await orchestrator.run(acb_ctx)
        except EstimationError as exc:
            return StructuredPipelineOutcome(
                bundle=None,
                final_status=FinalResponseStatus.ERROR,
                reason_code="estimation_failed",
                user_message=str(exc).strip() or "Unable to complete structured estimation.",
                technical_message=type(exc).__name__,
                audit_id=audit_id,
                safe_to_cache=False,
                safe_to_display=False,
                input_guardrail_results=input_phase.results,
                policy_outcomes=tuple(policy_parts),
            )

        bundle = acb_outcome.bundle
        ctx.prompt_version = bundle.prompt_version
        ctx.output_schema_version = bundle.result.schema_version
        ctx.rendered_prompt = RenderedPromptRef(
            prompt_version=bundle.prompt_version,
            examples_version=bundle.examples_version,
        )
        ctx.provider_metadata.update(
            {
                "acb_enabled": True,
                "acb_final_path": acb_outcome.final_path,
                "acb_iterations": len(acb_outcome.trace.iterations),
            }
        )

        return self._finalize_with_output_guardrails(
            request=request,
            bundle=bundle,
            ctx=ctx,
            audit_id=audit_id,
            input_phase_results=input_phase.results,
            policy_parts=policy_parts,
            cache_score_out=None,
            cache_bucket_out=None,
            cache_miss_out="acb_bypass",
            acb_trace=acb_outcome.trace,
        )

    def _finalize_with_output_guardrails(
        self,
        *,
        request: EstimationRequest,
        bundle: StructuredEstimateBundle,
        ctx: PipelineContext,
        audit_id: str,
        input_phase_results: tuple[GuardrailResult, ...],
        policy_parts: list[PolicyOutcome],
        cache_score_out: float | None,
        cache_bucket_out: str | None,
        cache_miss_out: str | None,
        acb_trace: AcbTrace | None = None,
    ) -> StructuredPipelineOutcome:
        out_started = perf_counter()
        out_results = evaluate_output_semantic_guardrails(
            request=request,
            result=bundle.result,
            settings=self._settings,
        )
        executor = PolicyExecutor(self._settings)
        out_policies: list[PolicyOutcome] = []
        final_bundle = bundle
        output_degraded = False
        degrade_reason: str | None = None
        degrade_message: str | None = None

        for res in out_results:
            po = executor.apply(res, audit_id=audit_id)
            out_policies.append(po)
            if res.passed or po.status != PolicyOutcomeStatus.ENFORCED:
                continue
            decl = guardrail_declaration_by_id(res.guardrail_id)
            if decl is None:
                continue
            if decl.on_fail == GuardrailPolicy.FILTER:
                output_degraded = True
                degrade_reason = {
                    "output_confidence_floor": "low_confidence",
                    "output_sensitive_leakage": "unsafe_output",
                    "output_useless_placeholder": "semantic_mismatch",
                }.get(res.guardrail_id, "unsafe_output")
                degrade_message = "The model output did not pass semantic safety checks."
                final_bundle = StructuredEstimateBundle(
                    result=build_degraded_estimation_result(user_summary=degrade_message),
                    prompt_version=bundle.prompt_version,
                    examples_version=bundle.examples_version,
                    model=bundle.model,
                    provider=bundle.provider,
                    usage=bundle.usage,
                    degraded=True,
                    finish_reason="output_guardrail_filter",
                )
                break

        ctx.validation_results.extend(out_results)
        ctx.timings_ms["output_semantic_ms"] = int((perf_counter() - out_started) * 1000)
        policy_parts.extend(out_policies)

        if output_degraded:
            if ctx.cache_metadata is not None:
                ctx.cache_metadata.safe_to_cache = False
            return StructuredPipelineOutcome(
                bundle=final_bundle,
                final_status=FinalResponseStatus.DEGRADED,
                reason_code=degrade_reason,
                user_message=degrade_message,
                technical_message=None,
                audit_id=audit_id,
                safe_to_cache=False,
                safe_to_display=True,
                input_guardrail_results=input_phase_results,
                output_guardrail_results=tuple(out_results),
                policy_outcomes=tuple(policy_parts),
                cache_score=cache_score_out,
                cache_bucket=cache_bucket_out,
                cache_miss_reason=cache_miss_out,
                acb_trace=acb_trace,
            )

        if ctx.cache_metadata is not None:
            ctx.cache_metadata.safe_to_cache = True

        return StructuredPipelineOutcome(
            bundle=final_bundle,
            final_status=FinalResponseStatus.SUCCESS,
            reason_code=None,
            user_message=None,
            technical_message=None,
            audit_id=audit_id,
            safe_to_cache=True,
            safe_to_display=True,
            input_guardrail_results=input_phase_results,
            output_guardrail_results=tuple(out_results),
            policy_outcomes=tuple(policy_parts),
            cached=False,
            cache_score=cache_score_out,
            cache_bucket=cache_bucket_out,
            cache_miss_reason=cache_miss_out,
            acb_trace=acb_trace,
        )
