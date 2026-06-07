"""Tests for ACB prompt bundle rendering."""

import json

from app.schemas.acb.critic import CriticFeedback, CriticIssue, CriticIssueCategory, CriticIssueSeverity
from app.schemas.estimation_result import (
    EstimationLineItem,
    EstimationPhase,
    EstimationResult,
    EstimationTotals,
)
from app.services.acb_prompt_rendering import (
    ACB_PROMPT_VERSION,
    render_acb_actor_prompts,
    render_acb_boss_prompts,
    render_acb_critic_prompts,
)


def _sample_candidate() -> EstimationResult:
    li = EstimationLineItem(name="Backend API", hours=40.0, cost_eur=2000.0)
    return EstimationResult(
        title="Sample project for ACB prompt tests",
        summary="A" * 30,
        phases=[EstimationPhase(name="Build", items=[li])],
        line_items=[],
        totals=EstimationTotals(hours=40.0, cost_eur=2000.0),
        duration_weeks=4.0,
        confidence=0.7,
    )


def test_acb_prompt_version_constant() -> None:
    assert ACB_PROMPT_VERSION == "acb/v1"


def test_role_system_prompts_are_structurally_distinct() -> None:
    actor = render_acb_actor_prompts(
        assessment_surface="Build a mobile app with auth.",
        project_metadata={"project_name": "Demo"},
        revision_instructions=None,
    )
    critic = render_acb_critic_prompts(
        candidate=_sample_candidate(),
        assessment_surface="Build a mobile app with auth.",
        project_metadata={"project_name": "Demo"},
    )
    boss = render_acb_boss_prompts(
        candidate=_sample_candidate(),
        critic_feedback=CriticFeedback(
            schema_version="1",
            overall_assessment="fail",
            issues=[
                CriticIssue(
                    category=CriticIssueCategory.risk_gap,
                    severity=CriticIssueSeverity.major,
                    message="Missing security risks.",
                    affected_area="risks",
                    suggested_fix="Add auth and data risks.",
                    evidence=None,
                )
            ],
            summary="Major risk gap.",
        ),
        iteration=1,
        max_iterations=2,
        budget_remaining=2,
    )

    assert actor.system_prompt != critic.system_prompt != boss.system_prompt
    assert "defect detection" in critic.system_prompt.lower()
    assert "process governance" in boss.system_prompt.lower()
    assert "generate" in actor.system_prompt.lower() or "candidate" in actor.system_prompt.lower()


def test_actor_revision_injects_boss_instructions() -> None:
    rendered = render_acb_actor_prompts(
        assessment_surface="Scope includes payments.",
        project_metadata={},
        revision_instructions="- Reconcile totals\n- Add PCI risks",
    )
    assert "Reconcile totals" in rendered.system_prompt or "Reconcile totals" in rendered.user_prompt
    assert "revision" in (rendered.system_prompt + rendered.user_prompt).lower()


def test_critic_user_includes_candidate_json() -> None:
    candidate = _sample_candidate()
    rendered = render_acb_critic_prompts(
        candidate=candidate,
        assessment_surface="Payments integration.",
        project_metadata={"industry": "fintech"},
    )
    payload = json.loads(candidate.model_dump_json())
    assert payload["title"] in rendered.user_prompt
    assert "Payments integration" in rendered.user_prompt


def test_boss_user_includes_critic_summary_and_budget() -> None:
    feedback = CriticFeedback(
        schema_version="1",
        overall_assessment="fail",
        issues=[],
        summary="Minor formatting only.",
    )
    rendered = render_acb_boss_prompts(
        candidate=_sample_candidate(),
        critic_feedback=feedback,
        iteration=2,
        max_iterations=2,
        budget_remaining=1,
    )
    assert "Minor formatting only" in rendered.user_prompt
    assert "2" in rendered.user_prompt
