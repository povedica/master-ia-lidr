"""Map simplified session submits to the guided ``EstimationRequest`` contract."""

from __future__ import annotations

from app.schemas.estimation_request import (
    Attachment,
    DetailLevel,
    EstimationRequest,
    OutputFormat,
)
from app.schemas.simplified_session import SessionEstimateRequest


def collect_context_warnings(request: SessionEstimateRequest) -> list[str]:
    """Return user-visible warnings for omitted simplified-form fields."""

    if request.industry is not None:
        return []
    return ["industry was not provided; industry-specific assumptions may be weaker"]


def adapt_to_estimation_request(
    request: SessionEstimateRequest,
    *,
    inline_attachments: list[Attachment],
    attachment_context: str,
) -> EstimationRequest:
    """Build a guided-form request for the structured estimation pipeline."""

    summary = _project_summary(request)
    description = _project_description(request, attachment_context)

    return EstimationRequest(
        project_name=request.project_name,
        project_summary=summary,
        project_type=request.project_type,
        target_audience=request.target_audience,
        industry=request.industry,
        project_description=description,
        detail_level=DetailLevel.medium,
        output_format=OutputFormat.phases_table,
        attachments=inline_attachments,
        preprocessing="none",
        evaluate=True,
    )


def _project_summary(request: SessionEstimateRequest) -> str:
    if request.one_line_summary and len(request.one_line_summary.strip()) >= 20:
        return request.one_line_summary.strip()[:200]
    text = request.transcript.strip()
    if len(text) >= 20:
        return text[:200]
    return (text + " project scope summary").strip()[:200]


def _project_description(request: SessionEstimateRequest, attachment_context: str) -> str:
    parts = [request.transcript.strip()]
    if request.additional_extra_info:
        parts.append(request.additional_extra_info.strip())
    if attachment_context.strip():
        parts.append("Attachment context:\n" + attachment_context.strip()[:4000])
    body = "\n\n".join(p for p in parts if p)
    if len(body) < 100:
        body = (body + " " + ("Additional project context. " * 8)).strip()
    return body[:24_000]
