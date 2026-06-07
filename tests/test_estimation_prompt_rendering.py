"""Estimation prompt rendering entry point."""

from app.context.examples import EstimationExample
from app.schemas.estimation_request import (
    DetailLevel,
    EstimationRequest,
    OutputFormat,
    ProjectType,
    TargetAudience,
)
from app.schemas.simplified_session import SessionEstimateRequest
from app.services.estimation_prompt_rendering import (
    render_estimation_prompt,
    render_session_system_prompt,
    render_session_turn_user_message,
)
from app.services.sessions import ProjectMetadata


def _minimal_request() -> EstimationRequest:
    return EstimationRequest(
        project_summary="A" * 25,
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_smb,
        project_description="B" * 120,
        detail_level=DetailLevel.medium,
        output_format=OutputFormat.phases_table,
    )


def test_render_estimation_prompt_includes_version_and_guided_fields() -> None:
    req = _minimal_request()
    ex = [
        EstimationExample(meeting_summary="m1", estimation="e1"),
        EstimationExample(meeting_summary="m2", estimation="e2"),
    ]
    out = render_estimation_prompt(
        req,
        examples=ex,
        preprocessing="none",
        preprocessed_requirements=None,
        version="v2",
        examples_version="fixture-v2",
    )
    assert out.prompt_version == "estimation/v2"
    assert out.examples_version == "fixture-v2"
    assert "medium" in out.user_prompt
    assert "phases_table" in out.user_prompt


def test_render_session_system_prompt_appends_populated_metadata_only() -> None:
    base = "You are an estimator."
    metadata = ProjectMetadata(
        project_name="Acme Portal",
        assumed_team_size=3,
        mentioned_technologies=["Python", "FastAPI"],
        agreed_scope="CRUD API for users",
        explicit_constraints=["Must use PostgreSQL"],
        rejected_options=["GraphQL"],
    )

    composed = render_session_system_prompt(base, metadata)

    assert composed.startswith(base)
    assert "Acme Portal" in composed
    assert "team size: 3" in composed.lower()
    assert "Python" in composed
    assert "FastAPI" in composed
    assert "CRUD API" in composed
    assert "PostgreSQL" in composed
    assert "GraphQL" in composed
    assert "None" not in composed


def test_render_session_system_prompt_omits_block_when_metadata_empty() -> None:
    composed = render_session_system_prompt("Base only.", ProjectMetadata())
    assert composed == "Base only."


def test_render_session_system_prompt_sparse_metadata_without_team_size() -> None:
    metadata = ProjectMetadata(
        project_name="Portal",
        agreed_scope="Ticket intake and dashboards",
    )
    composed = render_session_system_prompt("Base.", metadata)
    assert "Portal" in composed
    assert "team size" not in composed.lower()


def test_render_session_turn_user_message_first_turn_uses_full_guided_form() -> None:
    guided = _minimal_request()
    session_req = SessionEstimateRequest(
        project_name="Portal",
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_smb,
        transcript="We need a customer portal with billing integration and role-based access control for SMB clients.",
    )
    text = render_session_turn_user_message(session_req, guided, is_first_turn=True)
    assert "Contexto del producto" in text
    assert guided.project_description[:40] in text


def test_render_session_turn_user_message_subsequent_turn_is_delta_only() -> None:
    guided = _minimal_request()
    session_req = SessionEstimateRequest(
        project_name="Portal",
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_smb,
        transcript="Same portal project — add Redis caching for session tokens and keep the existing PostgreSQL datastore.",
    )
    text = render_session_turn_user_message(session_req, guided, is_first_turn=False)
    assert "## Turn update" in text
    assert "Redis caching" in text
    assert "Established project facts" in text
    assert guided.project_description not in text
