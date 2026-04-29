"""Adaptive estimation engine tests."""

from app.services.estimation_engine import EstimationMode, assess_and_select_mode


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
    _, mode = assess_and_select_mode(
        "We need something like a platform, not sure yet, maybe with dashboards etc."
    )
    assert mode == EstimationMode.EXPERT_REVIEW
