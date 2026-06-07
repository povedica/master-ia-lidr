"""Unit tests for ACB iteration policy pure functions."""

from app.guardrails.acb.policy import (
    actor_budget_remaining,
    budget_exhausted,
    count_issues_by_category,
    count_issues_by_severity,
    has_blocking_issues,
    normalize_boss_decision,
    should_continue_loop,
    suggest_boss_action_hint,
)
from app.schemas.acb.boss import BossAction, BossDecision
from app.schemas.acb.critic import (
    CriticFeedback,
    CriticIssue,
    CriticIssueCategory,
    CriticIssueSeverity,
)


def _issue(severity: CriticIssueSeverity) -> CriticIssue:
    return CriticIssue(
        category=CriticIssueCategory.scope_mismatch,
        severity=severity,
        message="Scope does not match transcript.",
        affected_area="scope",
        suggested_fix="Add missing mobile scope.",
        evidence=None,
    )


def _feedback(*issues: CriticIssue, overall: str = "fail") -> CriticFeedback:
    return CriticFeedback(
        schema_version="1",
        overall_assessment=overall,  # type: ignore[arg-type]
        issues=list(issues),
        summary="Assessment summary.",
    )


def test_minor_only_issues_suggest_accept() -> None:
    feedback = _feedback(_issue(CriticIssueSeverity.minor))
    hint = suggest_boss_action_hint(
        feedback,
        iteration=1,
        max_iterations=2,
        blocking_severities=frozenset({"critical", "major"}),
        allow_synthesize=True,
    )
    assert hint == BossAction.accept


def test_blocking_issue_with_budget_suggests_revise() -> None:
    feedback = _feedback(_issue(CriticIssueSeverity.major))
    hint = suggest_boss_action_hint(
        feedback,
        iteration=1,
        max_iterations=2,
        blocking_severities=frozenset({"critical", "major"}),
        allow_synthesize=True,
    )
    assert hint == BossAction.revise


def test_budget_exhausted_blocking_issues_suggest_synthesize() -> None:
    feedback = _feedback(_issue(CriticIssueSeverity.critical))
    hint = suggest_boss_action_hint(
        feedback,
        iteration=2,
        max_iterations=2,
        blocking_severities=frozenset({"critical", "major"}),
        allow_synthesize=True,
    )
    assert hint == BossAction.synthesize


def test_budget_exhausted_without_synthesize_suggests_accept() -> None:
    feedback = _feedback(_issue(CriticIssueSeverity.major))
    hint = suggest_boss_action_hint(
        feedback,
        iteration=2,
        max_iterations=2,
        blocking_severities=frozenset({"critical", "major"}),
        allow_synthesize=False,
    )
    assert hint == BossAction.accept


def test_normalize_clamps_revise_when_budget_exhausted() -> None:
    feedback = _feedback(_issue(CriticIssueSeverity.major))
    decision = BossDecision(
        action=BossAction.revise,
        reasoning="Try again",
        revision_instructions="- Fix totals",
        confidence_in_decision=0.7,
    )
    normalized = normalize_boss_decision(
        decision,
        iteration=2,
        max_iterations=2,
        feedback=feedback,
        blocking_severities=frozenset({"critical", "major"}),
        allow_synthesize=True,
    )
    assert normalized.action == BossAction.synthesize
    assert normalized.revision_instructions is None


def test_should_continue_loop_stops_on_accept_or_synthesize() -> None:
    accept = BossDecision(
        action=BossAction.accept,
        reasoning="Good enough",
        revision_instructions=None,
        confidence_in_decision=0.9,
    )
    synthesize = BossDecision(
        action=BossAction.synthesize,
        reasoning="Budget exhausted",
        revision_instructions=None,
        confidence_in_decision=0.6,
    )
    assert should_continue_loop(accept, iteration=1, max_iterations=2) is False
    assert should_continue_loop(synthesize, iteration=2, max_iterations=2) is False


def test_should_continue_loop_continues_revise_with_budget() -> None:
    revise = BossDecision(
        action=BossAction.revise,
        reasoning="Fix scope",
        revision_instructions="- Add API work",
        confidence_in_decision=0.75,
    )
    assert should_continue_loop(revise, iteration=1, max_iterations=2) is True
    assert should_continue_loop(revise, iteration=2, max_iterations=2) is False


def test_issue_count_helpers() -> None:
    issues = [
        _issue(CriticIssueSeverity.major),
        _issue(CriticIssueSeverity.minor),
    ]
    assert count_issues_by_severity(issues) == {"major": 1, "minor": 1}
    assert count_issues_by_category(issues) == {"scope_mismatch": 2}


def test_actor_budget_remaining_and_exhausted() -> None:
    assert actor_budget_remaining(1, max_iterations=2) == 2
    assert actor_budget_remaining(2, max_iterations=2) == 1
    assert budget_exhausted(1, max_iterations=2) is False
    assert budget_exhausted(2, max_iterations=2) is True


def test_has_blocking_issues_respects_severity_set() -> None:
    issues = [_issue(CriticIssueSeverity.minor)]
    assert has_blocking_issues(issues, blocking_severities=frozenset({"critical", "major"})) is False
    assert has_blocking_issues(
        [_issue(CriticIssueSeverity.critical)],
        blocking_severities=frozenset({"critical", "major"}),
    )
