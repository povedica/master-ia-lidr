"""Adaptive estimation engine tests."""

from app.services.estimation_engine import (
    EstimationMode,
    RequestAssessment,
    assess_and_select_mode,
    evaluate_mode_eligibility,
    input_quality_score_01,
    required_section_presence,
    summarize_assessment,
    validate_mode_output,
)


def test_input_quality_score_is_in_unit_interval() -> None:
    low = input_quality_score_01(RequestAssessment(0, 0, 0, 0))
    high = input_quality_score_01(RequestAssessment(20, 10, 0, 80))
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert high > low


def test_required_section_presence_maps_keys() -> None:
    text = "## Estimation\n### Assumptions\nx\n### Estimate\ny\n### Risks\nz\n"
    presence = required_section_presence(text, EstimationMode.BASIC)
    assert presence == {
        "assumption": True,
        "estimate": True,
        "risk": True,
    }


def test_input_quality_score_ambiguity_reduces_value() -> None:
    clear = input_quality_score_01(RequestAssessment(6, 2, 0, 30))
    vague = input_quality_score_01(RequestAssessment(6, 2, 4, 30))
    assert vague < clear


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
