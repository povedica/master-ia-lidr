"""Adapter from legacy domain guardrail helpers to ``GuardrailResult``."""

from __future__ import annotations

from app.guardrails.contracts import (
    GuardrailLayer,
    GuardrailPolicy,
    GuardrailResult,
    GuardrailSeverity,
)
from app.guardrails.policy_registry import guardrail_declaration_by_id
from app.services.domain_guardrails import check_estimation_domain


def evaluate_estimation_domain_relevance(surface: str) -> GuardrailResult:
    """Map ``check_estimation_domain`` into the shared guardrail contract."""

    decision = check_estimation_domain(surface)
    decl = guardrail_declaration_by_id("estimation_domain_relevance")
    policy = decl.on_fail if decl else GuardrailPolicy.FILTER
    passed = decision.accepted
    reasons: list[str] = []
    if not passed and decision.reason:
        reasons.append(decision.reason)
    elif not passed:
        reasons.append("domain_rejected")

    return GuardrailResult(
        guardrail_id="estimation_domain_relevance",
        layer=GuardrailLayer.INPUT_SEMANTIC,
        passed=passed,
        reasons=reasons,
        severity=GuardrailSeverity.MEDIUM if not passed else GuardrailSeverity.LOW,
        matched_rules=[decision.reason] if decision.reason else [],
        recommended_policy=policy,
        audit_payload={"domain_reason": decision.reason},
    )
