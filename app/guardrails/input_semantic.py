"""Compose semantic input guardrails (cheap checks before provider calls)."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.guardrails.contracts import (
    GuardrailPolicy,
    GuardrailResult,
    PolicyOutcome,
    PolicyOutcomeStatus,
    RolloutMode,
)
from app.guardrails.domain_adapter import evaluate_estimation_domain_relevance
from app.guardrails.exceptions import GuardrailViolationError
from app.guardrails.moderation import evaluate_moderation_placeholder
from app.guardrails.pii import evaluate_basic_pii
from app.guardrails.policy_executor import PolicyExecutor
from app.guardrails.policy_registry import guardrail_declaration_by_id
from app.guardrails.prompt_injection import evaluate_prompt_injection
from app.guardrails.rollout_resolution import effective_rollout


@dataclass(frozen=True)
class InputSemanticPhaseSummary:
    """Input semantic guardrail pass: results, policy outcomes, and optional early exit."""

    results: tuple[GuardrailResult, ...]
    outcomes: tuple[PolicyOutcome, ...]
    degraded: bool = False
    degrade_reason_code: str | None = None
    degrade_user_message: str | None = None
    degrade_guardrail_id: str | None = None


def _maybe_skip(decl_id: str, settings: Settings) -> bool:
    decl = guardrail_declaration_by_id(decl_id)
    if decl is None:
        return True
    return effective_rollout(decl, settings) == RolloutMode.DISABLED


async def run_input_semantic_phase(
    *,
    assessment_surface: str,
    guided_user_message: str,
    settings: Settings,
    audit_id: str,
) -> InputSemanticPhaseSummary:
    """Run ordered input semantic checks and apply registry policies."""

    executor = PolicyExecutor(settings)
    combined = f"{guided_user_message}\n{assessment_surface}"
    collected_results: list[GuardrailResult] = []
    collected_outcomes: list[PolicyOutcome] = []

    async def _consume(result: GuardrailResult) -> bool:
        """Return True when the caller must stop (degraded or exception raised)."""

        decl = guardrail_declaration_by_id(result.guardrail_id)
        if decl is None or effective_rollout(decl, settings) == RolloutMode.DISABLED:
            return False
        outcome = executor.apply(result, audit_id=audit_id)
        collected_results.append(result)
        collected_outcomes.append(outcome)
        if result.passed or outcome.status != PolicyOutcomeStatus.ENFORCED:
            return False
        if decl.on_fail == GuardrailPolicy.EXCEPTION:
            reason = "unsafe_input"
            message = "This request cannot be processed safely."
            if result.guardrail_id == "estimation_domain_relevance":
                reason = "out_of_scope"
                message = "Only software/project estimation requests are supported."
            elif result.guardrail_id == "prompt_injection_patterns":
                message = "Potential prompt manipulation was detected in the request."
            elif result.guardrail_id == "pii_basic":
                message = "Personal or sensitive patterns were detected in the request."
            raise GuardrailViolationError(
                guardrail_id=result.guardrail_id,
                reason_code=reason,
                user_message=message,
                audit_id=audit_id,
            )
        if decl.on_fail == GuardrailPolicy.FILTER:
            msg = "Only software or IT project estimation requests are supported for this endpoint."
            if result.guardrail_id == "estimation_domain_relevance":
                msg = "This request looks outside the estimation scope for this service."
            return True
        return False

    if not _maybe_skip("prompt_injection_patterns", settings):
        inj = evaluate_prompt_injection(combined)
        if await _consume(inj):
            return InputSemanticPhaseSummary(
                tuple(collected_results),
                tuple(collected_outcomes),
                degraded=True,
                degrade_reason_code="unsafe_input",
                degrade_user_message="Potential prompt manipulation was detected in the request.",
                degrade_guardrail_id=inj.guardrail_id,
            )

    if not _maybe_skip("pii_basic", settings):
        pii = evaluate_basic_pii(combined)
        if await _consume(pii):
            return InputSemanticPhaseSummary(
                tuple(collected_results),
                tuple(collected_outcomes),
                degraded=True,
                degrade_reason_code="unsafe_input",
                degrade_user_message="Personal or sensitive patterns were detected in the request.",
                degrade_guardrail_id=pii.guardrail_id,
            )

    if settings.llm_domain_guardrail_enabled and not _maybe_skip("estimation_domain_relevance", settings):
        surface = assessment_surface.strip() or guided_user_message.strip()
        domain = evaluate_estimation_domain_relevance(surface)
        decl = guardrail_declaration_by_id("estimation_domain_relevance")
        if decl and effective_rollout(decl, settings) != RolloutMode.DISABLED:
            outcome = executor.apply(domain, audit_id=audit_id)
            collected_results.append(domain)
            collected_outcomes.append(outcome)
            if not domain.passed and outcome.status == PolicyOutcomeStatus.ENFORCED:
                if decl.on_fail == GuardrailPolicy.EXCEPTION:
                    raise GuardrailViolationError(
                        guardrail_id=domain.guardrail_id,
                        reason_code="out_of_scope",
                        user_message="Only software/project estimation requests are supported.",
                        audit_id=audit_id,
                    )
                if decl.on_fail == GuardrailPolicy.FILTER:
                    return InputSemanticPhaseSummary(
                        tuple(collected_results),
                        tuple(collected_outcomes),
                        degraded=True,
                        degrade_reason_code="out_of_scope",
                        degrade_user_message="This request looks outside the estimation scope for this service.",
                        degrade_guardrail_id=domain.guardrail_id,
                    )

    if not _maybe_skip("moderation_toxicity", settings):
        mod = await evaluate_moderation_placeholder(combined)
        if await _consume(mod):
            return InputSemanticPhaseSummary(
                tuple(collected_results),
                tuple(collected_outcomes),
                degraded=True,
                degrade_reason_code="unsafe_input",
                degrade_user_message="Moderation policy rejected this request.",
                degrade_guardrail_id=mod.guardrail_id,
            )

    return InputSemanticPhaseSummary(tuple(collected_results), tuple(collected_outcomes))
