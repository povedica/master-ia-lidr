"""Pure iteration policy helpers for Actor-Critic-Boss orchestration."""

from __future__ import annotations

from app.schemas.acb.boss import BossAction, BossDecision
from app.schemas.acb.critic import CriticFeedback, CriticIssue, CriticIssueSeverity


def count_issues_by_severity(issues: list[CriticIssue]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        key = issue.severity.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def count_issues_by_category(issues: list[CriticIssue]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        key = issue.category.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def has_blocking_issues(
    issues: list[CriticIssue],
    *,
    blocking_severities: frozenset[str],
) -> bool:
    return any(issue.severity.value in blocking_severities for issue in issues)


def actor_budget_remaining(
    iteration: int,
    *,
    max_iterations: int,
) -> int:
    """Return remaining Actor passes including the current iteration."""
    return max(0, max_iterations - iteration + 1)


def budget_exhausted(iteration: int, *, max_iterations: int) -> bool:
    return iteration >= max_iterations


def suggest_boss_action_hint(
    feedback: CriticFeedback,
    *,
    iteration: int,
    max_iterations: int,
    blocking_severities: frozenset[str],
    allow_synthesize: bool,
) -> BossAction:
    """Deterministic policy hint; Boss LLM may override with reasoning."""

    if feedback.overall_assessment == "pass" and not feedback.issues:
        return BossAction.accept

    if not has_blocking_issues(feedback.issues, blocking_severities=blocking_severities):
        return BossAction.accept

    if not budget_exhausted(iteration, max_iterations=max_iterations):
        return BossAction.revise

    if allow_synthesize:
        return BossAction.synthesize

    return BossAction.accept


def normalize_boss_decision(
    decision: BossDecision,
    *,
    iteration: int,
    max_iterations: int,
    feedback: CriticFeedback,
    blocking_severities: frozenset[str],
    allow_synthesize: bool,
) -> BossDecision:
    """Clamp Boss output to iteration budget and policy guardrails."""

    hint = suggest_boss_action_hint(
        feedback,
        iteration=iteration,
        max_iterations=max_iterations,
        blocking_severities=blocking_severities,
        allow_synthesize=allow_synthesize,
    )

    if decision.action == BossAction.revise and budget_exhausted(iteration, max_iterations=max_iterations):
        if allow_synthesize:
            return decision.model_copy(
                update={
                    "action": BossAction.synthesize,
                    "revision_instructions": None,
                }
            )
        return decision.model_copy(
            update={
                "action": BossAction.accept,
                "revision_instructions": None,
            }
        )

    if decision.action == BossAction.revise and not has_blocking_issues(
        feedback.issues,
        blocking_severities=blocking_severities,
    ):
        return decision.model_copy(
            update={
                "action": BossAction.accept,
                "revision_instructions": None,
            }
        )

    if decision.action == BossAction.synthesize and not allow_synthesize:
        return decision.model_copy(update={"action": hint})

    if decision.action == BossAction.revise and decision.revision_instructions is None:
        return decision.model_copy(update={"action": BossAction.accept})

    return decision


def should_continue_loop(
    decision: BossDecision,
    *,
    iteration: int,
    max_iterations: int,
) -> bool:
    if decision.action == BossAction.accept:
        return False
    if decision.action == BossAction.synthesize:
        return False
    if decision.action == BossAction.revise:
        return iteration < max_iterations
    return False
