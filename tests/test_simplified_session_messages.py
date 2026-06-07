"""Unit tests for session turn history message compaction."""

from app.schemas.estimation_request import ProjectType, TargetAudience
from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from app.schemas.simplified_session import SessionEstimateRequest
from app.services.simplified_session_estimation_service import (
    _assistant_history_message,
    _user_history_message,
)


def test_user_history_message_uses_turn_index_and_transcript() -> None:
    request = SessionEstimateRequest(
        project_name="Portal",
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_smb,
        transcript="Same portal project — add Redis caching for session tokens and keep the existing PostgreSQL datastore.",
    )
    text = _user_history_message(request, turn_index=2)
    assert text.startswith("[Turn 2]")
    assert "Redis caching" in text


def test_assistant_history_message_ends_with_complete_totals_suffix() -> None:
    result = EstimationResult(
        title="Acme Portal",
        summary="Structured estimate for a B2B SaaS portal with authentication and billing.",
        phases=[],
        line_items=[EstimationLineItem(name="Auth", hours=10.0, cost_eur=580.0)],
        totals=EstimationTotals(hours=10.0, cost_eur=580.0),
        duration_weeks=4.0,
        confidence=0.8,
    )
    text = _assistant_history_message(result)
    assert text.startswith("Estimate «Acme Portal»:")
    assert text.endswith("Totals: 10h.")
    assert "..." not in text or text.count("...") <= 1
