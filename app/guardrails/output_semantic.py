"""Semantic checks on structured estimation output (post-schema validation)."""

from __future__ import annotations

import json
import re

from app.config import Settings
from app.guardrails.contracts import (
    GuardrailLayer,
    GuardrailPolicy,
    GuardrailResult,
    GuardrailSeverity,
    OutputSemanticGuardrailResult,
    RolloutMode,
)
from app.guardrails.policy_registry import guardrail_declaration_by_id
from app.guardrails.rollout_resolution import effective_rollout
from app.schemas.estimation_request import EstimationRequest
from app.schemas.estimation_result import EstimationResult


_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def evaluate_output_semantic_guardrails(
    *,
    request: EstimationRequest,
    result: EstimationResult,
    settings: Settings,
) -> list[GuardrailResult]:
    """Run deterministic output semantic checks (registry rollout respected)."""

    del request  # reserved for mismatch heuristics
    results: list[GuardrailResult] = []

    decl_conf = guardrail_declaration_by_id("output_confidence_floor")
    if decl_conf and effective_rollout(decl_conf, settings) != RolloutMode.DISABLED:
        floor = settings.estimation_min_output_confidence
        passed = result.confidence >= floor
        results.append(
            OutputSemanticGuardrailResult(
                guardrail_id="output_confidence_floor",
                layer=GuardrailLayer.OUTPUT_SEMANTIC,
                passed=passed,
                reasons=[] if passed else ["confidence_below_minimum"],
                severity=GuardrailSeverity.MEDIUM if not passed else GuardrailSeverity.LOW,
                recommended_policy=GuardrailPolicy.FILTER,
                audit_payload={"floor": floor, "confidence": result.confidence},
                safe_fallback_needed=not passed,
            )
        )

    decl_leak = guardrail_declaration_by_id("output_sensitive_leakage")
    if decl_leak and effective_rollout(decl_leak, settings) != RolloutMode.DISABLED:
        blob = json.dumps(result.model_dump(), ensure_ascii=False)
        emails = _EMAIL_RE.findall(blob)
        passed = not emails
        results.append(
            OutputSemanticGuardrailResult(
                guardrail_id="output_sensitive_leakage",
                layer=GuardrailLayer.OUTPUT_SEMANTIC,
                passed=passed,
                reasons=[] if passed else ["email_like_pattern_in_output"],
                severity=GuardrailSeverity.HIGH if not passed else GuardrailSeverity.LOW,
                recommended_policy=GuardrailPolicy.FILTER,
                redaction_applied=False,
                audit_payload={"email_match_count": len(emails)},
                safe_fallback_needed=not passed,
            )
        )

    decl_useless = guardrail_declaration_by_id("output_useless_placeholder")
    if decl_useless and effective_rollout(decl_useless, settings) != RolloutMode.DISABLED:
        summary = result.summary.strip()
        generic = summary.lower().startswith("estimate") and len(summary) < 80
        thin = len(summary) < 35 and result.confidence >= 0.55
        passed = not (generic or thin)
        results.append(
            OutputSemanticGuardrailResult(
                guardrail_id="output_useless_placeholder",
                layer=GuardrailLayer.OUTPUT_SEMANTIC,
                passed=passed,
                reasons=[] if passed else ["generic_or_thin_summary"],
                severity=GuardrailSeverity.LOW,
                recommended_policy=GuardrailPolicy.FILTER,
                audit_payload={"summary_len": len(summary)},
                safe_fallback_needed=False,
            )
        )

    return results
