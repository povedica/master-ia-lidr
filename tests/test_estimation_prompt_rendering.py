"""Estimation prompt rendering entry point."""

from app.context.examples import EstimationExample
from app.schemas.estimation_request import (
    DataSensitivity,
    DeliveryUrgency,
    DetailLevel,
    EstimationRequest,
    OutputFormat,
    ProjectType,
    TargetAudience,
)
from app.services.estimation_engine import EstimationMode
from app.services.estimation_prompt_rendering import render_estimation_prompt


def _minimal_request() -> EstimationRequest:
    return EstimationRequest(
        project_summary="A" * 25,
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_smb,
        project_description="B" * 120,
        deliverables=["d1", "d2", "d3"],
        delivery_urgency=DeliveryUrgency.flexible,
        data_sensitivity=DataSensitivity.public_only,
        detail_level=DetailLevel.medium,
        output_format=OutputFormat.phases_table,
    )


def test_render_estimation_prompt_includes_mode_and_version() -> None:
    req = _minimal_request()
    ex = [
        EstimationExample(meeting_summary="m1", estimation="e1"),
        EstimationExample(meeting_summary="m2", estimation="e2"),
    ]
    out = render_estimation_prompt(
        req,
        mode=EstimationMode.STANDARD,
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
