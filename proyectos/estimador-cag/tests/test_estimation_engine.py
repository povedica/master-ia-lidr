"""Adaptive estimation engine tests."""

from app.services.estimation_engine import (
    EstimationMode,
    assess_and_select_mode,
    evaluate_mode_eligibility,
    summarize_assessment,
    validate_mode_output,
)


def test_routes_short_request_to_basic() -> None:
    _, mode = assess_and_select_mode(
        "Need a login page and simple contact form for a startup website."
    )
    assert mode == EstimationMode.BASIC


def test_routes_typical_request_to_standard() -> None:
    _, mode = assess_and_select_mode(
        "The client needs an ecommerce site with catalog, checkout, and order tracking."
    )
    assert mode == EstimationMode.STANDARD


def test_routes_detailed_request_to_professional() -> None:
    _, mode = assess_and_select_mode(
        "The client needs an admin dashboard with SSO, role-based auth, API integrations, "
        "backend services, frontend views, database migrations, testing strategy, delivery "
        "timeline, and clear scope constraints for each module."
    )
    assert mode == EstimationMode.PROFESSIONAL


def test_routes_ambiguous_request_to_expert_review() -> None:
    assessment, mode = assess_and_select_mode(
        "We need something like a platform, not sure yet, maybe with dashboards etc."
    )
    assert mode == EstimationMode.EXPERT_REVIEW
    summary = summarize_assessment(assessment, mode)
    eligibility = evaluate_mode_eligibility(summary)
    assert summary.detail_level == "low"
    assert EstimationMode.EXPERT_REVIEW in eligibility.blocked_modes
    assert EstimationMode.STANDARD in eligibility.allowed_modes


def test_expert_review_validation_requires_profile_keyword() -> None:
    """Expert mode output must include a profile breakdown (validated via normalized keyword)."""

    without_profile = (
        "## Assumptions\nok\n## Gaps & Missing Information\nok\n## Uncertainty\nok\n## Recommendations\nok\n"
    )
    assert validate_mode_output(without_profile, EstimationMode.EXPERT_REVIEW) is False

    with_profile = without_profile + "## Profile breakdown\nok\n"
    assert validate_mode_output(with_profile, EstimationMode.EXPERT_REVIEW) is True
