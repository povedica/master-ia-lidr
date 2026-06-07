"""ACB orchestration Pydantic schemas (Critic, Boss, trace)."""

import pytest
from pydantic import ValidationError

from app.schemas.acb.boss import BossAction, BossDecision
from app.schemas.acb.critic import (
    CriticFeedback,
    CriticIssue,
    CriticIssueCategory,
    CriticIssueSeverity,
)
from app.schemas.acb.trace import AcbIterationRecord, AcbTrace


def test_critic_feedback_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CriticFeedback(
            schema_version="1",
            overall_assessment="pass",
            issues=[],
            summary="No issues found.",
            unexpected_field=True,  # type: ignore[call-arg]
        )


def test_critic_feedback_pass_with_empty_issues() -> None:
    feedback = CriticFeedback(
        schema_version="1",
        overall_assessment="pass",
        issues=[],
        summary="Candidate is coherent with metadata.",
    )
    assert feedback.overall_assessment == "pass"
    assert feedback.issues == []


def test_critic_issue_enums_and_fields() -> None:
    issue = CriticIssue(
        category=CriticIssueCategory.arithmetic_inconsistency,
        severity=CriticIssueSeverity.major,
        message="Phase totals do not sum to project total.",
        affected_area="totals",
        suggested_fix="Reconcile phase hours with line items.",
        evidence="Phase 1: 40h, declared total: 30h",
    )
    assert issue.category == CriticIssueCategory.arithmetic_inconsistency
    assert issue.severity == CriticIssueSeverity.major


def test_critic_feedback_has_no_estimate_field_in_schema() -> None:
    schema = CriticFeedback.model_json_schema()
    props = schema.get("properties", {})
    assert "estimate" not in props
    assert "estimation_result" not in props
    assert "replacement_estimate" not in props


def test_boss_decision_accepts_revise_with_instructions() -> None:
    decision = BossDecision(
        action=BossAction.revise,
        reasoning="Major arithmetic gap is localized and fixable in one pass.",
        revision_instructions="- Reconcile phase totals\n- Update risk section",
        confidence_in_decision=0.82,
    )
    assert decision.action == BossAction.revise
    assert decision.revision_instructions is not None


def test_boss_decision_rejects_invalid_action() -> None:
    with pytest.raises(ValidationError):
        BossDecision(
            action="rewrite",  # type: ignore[arg-type]
            reasoning="Invalid action should fail.",
            revision_instructions=None,
            confidence_in_decision=0.5,
        )


def test_acb_trace_records_iterations() -> None:
    record = AcbIterationRecord(
        iteration=1,
        boss_action=BossAction.accept,
        critic_issue_counts={"major": 0, "minor": 1},
        actor_model="gpt-4o-mini",
        critic_model="gpt-4o-mini",
        boss_model="gpt-4o-mini",
        timings_ms={"actor": 120, "critic": 80, "boss": 60},
        usage=None,
    )
    trace = AcbTrace(
        enabled=True,
        iterations=[record],
        final_path="accept",
        total_usage=None,
        prompt_version_acb="acb/v1",
    )
    assert trace.enabled is True
    assert len(trace.iterations) == 1
    assert trace.final_path == "accept"
