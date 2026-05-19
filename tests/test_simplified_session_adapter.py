"""Unit tests for simplified session → guided form adapter."""

from __future__ import annotations

from app.schemas.estimation_request import Industry, ProjectType, TargetAudience
from app.schemas.simplified_session import SessionEstimateRequest
from app.services.simplified_session_adapter import (
    adapt_to_estimation_request,
    collect_context_warnings,
)


def test_collect_context_warnings_includes_industry_gap() -> None:
    request = SessionEstimateRequest(
        project_name="Portal",
        project_type=ProjectType.web_saas,
        transcript="A" * 80,
        target_audience=TargetAudience.b2b_smb,
    )
    warnings = collect_context_warnings(request)
    assert any("industry" in w for w in warnings)


def test_collect_context_warnings_omits_removed_guided_form_fields() -> None:
    request = SessionEstimateRequest(
        project_name="Portal",
        project_type=ProjectType.web_saas,
        transcript="A" * 80,
        target_audience=TargetAudience.b2b_smb,
    )
    warnings = collect_context_warnings(request)
    joined = " ".join(warnings).lower()
    assert "delivery urgency" not in joined
    assert "data sensitivity" not in joined
    assert "detail level" not in joined
    assert "output format" not in joined


def test_collect_context_warnings_empty_when_industry_provided() -> None:
    request = SessionEstimateRequest(
        project_name="Portal",
        project_type=ProjectType.web_saas,
        transcript="A" * 80,
        target_audience=TargetAudience.b2b_smb,
        industry=Industry.fintech,
    )
    assert collect_context_warnings(request) == []


def test_adapt_to_estimation_request_builds_valid_guided_payload() -> None:
    request = SessionEstimateRequest(
        project_name="Portal",
        one_line_summary="Partner portal for ticket intake and reporting",
        project_type=ProjectType.web_saas,
        transcript="A" * 120,
        target_audience=TargetAudience.b2b_smb,
        industry=Industry.fintech,
    )
    guided = adapt_to_estimation_request(
        request,
        inline_attachments=[],
        attachment_context="",
    )
    assert guided.project_name == "Portal"
    assert len(guided.deliverables) >= 3
    assert len(guided.project_description) >= 100
