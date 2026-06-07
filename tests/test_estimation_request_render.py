"""Golden-style tests for guided-form user message rendering."""

from __future__ import annotations

from app.schemas.estimation_request import (
    Attachment,
    DetailLevel,
    EstimationRequest,
    Industry,
    OutputFormat,
    ProjectType,
    TargetAudience,
)
from app.services.estimation_request_render import (
    render_estimation_assessment_surface,
    render_estimation_user_message,
    user_message_template_version,
)
from app.services.estimation_prompt_rendering import (
    render_assessment_surface,
    render_guided_user_message,
)


def _full_request() -> EstimationRequest:
    raw = __import__("base64").b64encode(b"Hello attachment.").decode("ascii")
    return EstimationRequest(
        project_name="ACME",
        project_summary="Twenty chars minimum!!",
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_smb,
        industry=Industry.fintech,
        project_description="x" * 100,
        detail_level=DetailLevel.detailed,
        output_format=OutputFormat.line_items,
        attachments=[
            Attachment(
                filename="brief.txt",
                content_type="text/plain",
                content_base64=raw,
            )
        ],
        preprocessing="none",
        evaluate=True,
    )


def test_user_message_template_version_is_stable() -> None:
    assert user_message_template_version() == "guided-form-v2"


def test_render_estimation_assessment_surface_joins_core_fields() -> None:
    req = _full_request()
    surface = render_estimation_assessment_surface(req)
    assert req.project_summary in surface
    assert req.project_description in surface
    assert "Contexto del producto" not in surface


def test_render_estimation_user_message_snapshot() -> None:
    text = render_estimation_user_message(_full_request())
    assert text.endswith("\n")
    assert "## Contexto del producto" in text
    assert "**Nombre / código:** ACME" in text
    assert "**Tipo de proyecto:** web_saas" in text
    assert "## Descripción del proyecto" in text
    assert "x" * 100 in text
    assert "## Preferencias de salida" in text
    assert "detailed" in text
    assert "## Documentos de apoyo" in text
    assert "Hello attachment." in text
    assert "## Integraciones y datos" not in text
    assert "## Riesgos" not in text
    assert "## Alcance" not in text


def test_v1_v2_guided_and_assessment_parity_on_full_fixture() -> None:
    req = _full_request()
    guided_v1 = render_guided_user_message(req, version="v1")
    guided_v2 = render_guided_user_message(req, version="v2")
    assert guided_v1 == guided_v2
    surface_v1 = render_assessment_surface(req, version="v1")
    surface_v2 = render_assessment_surface(req, version="v2")
    assert surface_v1 == surface_v2
    assert render_estimation_user_message(req, version="v1") == render_estimation_user_message(
        req, version="v2"
    )
    assert render_estimation_assessment_surface(req, version="v1") == render_estimation_assessment_surface(
        req, version="v2"
    )
