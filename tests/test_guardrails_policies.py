"""Tests for guardrail policy registry and core policy contracts."""

from __future__ import annotations

from app.guardrails.contracts import (
    GuardrailLayer,
    GuardrailPolicy,
    GuardrailResult,
    GuardrailSeverity,
    OutputSemanticGuardrailResult,
    PolicyOutcome,
    PolicyOutcomeStatus,
    RolloutMode,
)
from app.guardrails.policy_registry import iter_guardrail_declarations


def test_registry_declarations_have_unique_ids_sorted() -> None:
    decls = list(iter_guardrail_declarations())
    ids = [d.id for d in decls]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


def test_each_declaration_has_valid_on_fail_rollout_and_rules_version() -> None:
    for decl in iter_guardrail_declarations():
        assert isinstance(decl.on_fail, GuardrailPolicy)
        assert isinstance(decl.rollout, RolloutMode)
        assert decl.retry_max >= 0
        assert decl.rules_version.strip()


def test_guardrail_result_minimal_success() -> None:
    result = GuardrailResult(
        guardrail_id="unit_test",
        layer=GuardrailLayer.INPUT_SEMANTIC,
        passed=True,
        reasons=[],
        severity=GuardrailSeverity.LOW,
        recommended_policy=GuardrailPolicy.FILTER,
    )
    assert result.passed is True
    assert result.matched_rules == []
    assert result.moderation_scores == {}


def test_policy_outcome_minimal() -> None:
    outcome = PolicyOutcome(
        guardrail_id="unit_test",
        policy=GuardrailPolicy.EXCEPTION,
        status=PolicyOutcomeStatus.RECORDED_LOG_ONLY,
        reason_code="test_reason",
    )
    assert outcome.retry_allowed is False
    assert outcome.retry_after_fix is False
    assert outcome.fallback_response is None


def test_output_semantic_guardrail_result_extends_base() -> None:
    out = OutputSemanticGuardrailResult(
        guardrail_id="out_sem",
        layer=GuardrailLayer.OUTPUT_SEMANTIC,
        passed=False,
        reasons=["low_confidence"],
        severity=GuardrailSeverity.MEDIUM,
        recommended_policy=GuardrailPolicy.FILTER,
        redaction_applied=True,
        safe_fallback_needed=True,
    )
    assert out.redaction_applied is True
    assert out.safe_fallback_needed is True
