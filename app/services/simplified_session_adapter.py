"""Map simplified session submits to the guided ``EstimationRequest`` contract."""

from __future__ import annotations

import re

from app.schemas.estimation_request import (
    Attachment,
    DataSensitivity,
    DeliveryUrgency,
    DetailLevel,
    EstimationRequest,
    OutputFormat,
)
from app.schemas.simplified_session import SessionEstimateRequest

_DELIVERABLE_MIN_LEN = 20


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
    deliverables = _derive_deliverables(request.transcript)

    return EstimationRequest(
        project_name=request.project_name,
        project_summary=summary,
        project_type=request.project_type,
        target_audience=request.target_audience,
        industry=request.industry,
        project_description=description,
        deliverables=deliverables,
        delivery_urgency=DeliveryUrgency.flexible,
        data_sensitivity=DataSensitivity.regulated_unknown,
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


def _derive_deliverables(transcript: str) -> list[str]:
    candidates: list[str] = []
    for line in transcript.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] in "-*•":
            item = stripped.lstrip("-*• ").strip()
        elif re.match(r"^\d+[.)]\s+", stripped):
            item = re.sub(r"^\d+[.)]\s+", "", stripped).strip()
        else:
            continue
        if len(item) >= _DELIVERABLE_MIN_LEN:
            candidates.append(item[:80])

    base = transcript.strip()
    while len(candidates) < 3:
        index = len(candidates)
        start = index * max(_DELIVERABLE_MIN_LEN, len(base) // 3)
        chunk = base[start : start + 80].strip()
        if len(chunk) < _DELIVERABLE_MIN_LEN:
            chunk = (chunk + " delivery scope item").strip()[:80]
        if len(chunk) < _DELIVERABLE_MIN_LEN:
            chunk = (chunk + "x" * _DELIVERABLE_MIN_LEN)[:80]
        candidates.append(chunk)

    return candidates[:8]
