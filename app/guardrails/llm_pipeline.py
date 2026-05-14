"""Guarded structured estimation pipeline (v2 orchestration)."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from app.config import Settings
from app.guardrails.audit import new_audit_id
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
from app.services.estimation_engine import (
    assess_and_select_mode,
    enforce_mode_eligibility,
    evaluate_mode_eligibility,
    summarize_assessment,
)
from app.services.estimation_request_render import render_estimation_user_message
from app.services.llm_service import EstimationError, EstimationService, StructuredEstimateBundle


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


class LLMPipeline:
    """Coordinates input guardrails, provider call, and output semantic validation."""

    def __init__(self, service: EstimationService, settings: Settings) -> None:
        self._service = service
        self._settings = settings

    async def run_structured(
        self,
        request: EstimationRequest,
        *,
        assessment_surface: str,
        request_id: str,
    ) -> StructuredPipelineOutcome:
        """Execute the guarded v2 path (raises ``GuardrailViolationError`` on enforced blocks)."""

        audit_id = new_audit_id()
        started = perf_counter()
        guided = render_estimation_user_message(request).strip()
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
            raw, rec_mode = assess_and_select_mode(surface)
            assessment = summarize_assessment(raw, rec_mode)
            eligibility = evaluate_mode_eligibility(assessment)
            mode = enforce_mode_eligibility(rec_mode, eligibility)
            bundle = StructuredEstimateBundle(
                result=degraded_result,
                prompt_version="guardrail/degraded",
                examples_version="guardrail/degraded",
                mode=mode,
                model="guardrail",
                provider="guardrail",
                usage=None,
                degraded=True,
                finish_reason="guardrail_filter",
                assessment=assessment,
                mode_eligibility=eligibility,
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

        try:
            bundle = await self._service.estimate_structured(
                request,
                assessment_surface=assessment_surface,
                skip_domain_guardrail=True,
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
                    mode=bundle.mode,
                    model=bundle.model,
                    provider=bundle.provider,
                    usage=bundle.usage,
                    degraded=True,
                    finish_reason="output_guardrail_filter",
                    assessment=bundle.assessment,
                    mode_eligibility=bundle.mode_eligibility,
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
            input_guardrail_results=input_phase.results,
            output_guardrail_results=tuple(out_results),
            policy_outcomes=tuple(policy_parts),
        )
