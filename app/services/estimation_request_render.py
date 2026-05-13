"""Render structured ``EstimationRequest`` into the user message for the LLM pipeline."""

from __future__ import annotations

import base64
from typing import Final

from app.schemas.estimation_request import EstimationRequest, Industry, TargetAudience

USER_MESSAGE_TEMPLATE_VERSION: Final[str] = "guided-form-v1"

# Section titles in Spanish to reduce accidental matches with English keyword heuristics
# in ``estimation_engine.assess_request`` (see docs/technical/README.md).


def render_estimation_assessment_surface(request: EstimationRequest) -> str:
    """Narrow text for domain guardrail + adaptive mode selection.

    Uses user-authored summary, narrative, and scope bullets only — not the full
    Markdown template headers — so keyword-based heuristics stay aligned with user intent.
    """

    chunks: list[str] = [request.project_summary, request.project_description]
    chunks.extend(request.deliverables)
    if request.out_of_scope:
        chunks.extend(request.out_of_scope)
    return "\n\n".join(c.strip() for c in chunks if c and c.strip())


def _attachment_inline_note(request: EstimationRequest) -> list[str]:
    lines: list[str] = []
    for att in request.attachments:
        if att.content_type == "application/pdf":
            lines.append(f"- PDF «{att.filename}» (binary; no OCR — filename and type only).")
            continue
        raw = base64.b64decode("".join(att.content_base64.split()), validate=True)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        text = text.strip()
        if not text:
            lines.append(f"- «{att.filename}» ({att.content_type}): (empty after decode)")
        else:
            lines.append(f"- «{att.filename}» ({att.content_type}):\n{text}")
    return lines


def render_estimation_user_message(request: EstimationRequest) -> str:
    """Build the full user message passed to ``EstimationService`` (Markdown, deterministic layout)."""

    parts: list[str] = []

    parts.append("## Contexto del producto\n")
    if request.project_name:
        parts.append(f"- **Nombre / código:** {request.project_name}\n")
    parts.append(f"- **Resumen:** {request.project_summary}\n")
    parts.append(f"- **Tipo de proyecto:** {request.project_type.value}\n")
    aud = request.target_audience.value
    if request.target_audience == TargetAudience.other and request.target_audience_other:
        aud = f"{aud} ({request.target_audience_other})"
    parts.append(f"- **Audiencia objetivo:** {aud}\n")
    if request.industry is not None:
        ind = request.industry.value
        if request.industry == Industry.other and request.industry_other:
            ind = f"{ind} ({request.industry_other})"
        parts.append(f"- **Sector:** {ind}\n")

    parts.append("\n## Descripción del proyecto\n\n")
    parts.append(request.project_description.strip())
    parts.append("\n")

    parts.append("\n## Alcance\n")
    parts.append("### Entregables\n")
    for d in request.deliverables:
        parts.append(f"- {d}\n")
    if request.out_of_scope:
        parts.append("\n### Fuera de alcance\n")
        for line in request.out_of_scope:
            parts.append(f"- {line}\n")

    parts.append("\n## Entrega y plazos\n")
    parts.append(f"- **Urgencia:** {request.delivery_urgency.value}\n")
    if request.target_date is not None:
        parts.append(f"- **Fecha objetivo:** {request.target_date.isoformat()}\n")
    if request.delivery_approach is not None:
        parts.append(f"- **Enfoque de entrega:** {request.delivery_approach.value}\n")

    parts.append("\n## Integraciones y datos\n")
    if request.integration_categories:
        cats = ", ".join(c.value for c in request.integration_categories)
        parts.append(f"- **Integraciones:** {cats}\n")
    else:
        parts.append("- **Integraciones:** (ninguna indicada)\n")
    if request.integration_custom_names:
        parts.append(
            "- **Integraciones (nombres propios):** "
            + "; ".join(request.integration_custom_names)
            + "\n"
        )
    parts.append(f"- **Sensibilidad de datos:** {request.data_sensitivity.value}\n")

    parts.append("\n## Restricciones y entorno\n")
    if request.hosting_constraints:
        hc = ", ".join(h.value for h in request.hosting_constraints)
        parts.append(f"- **Alojamiento / despliegue:** {hc}\n")
    if request.hosting_notes:
        parts.append(f"- **Notas de alojamiento:** {request.hosting_notes}\n")
    if request.team_context is not None:
        parts.append(f"- **Contexto de equipo:** {request.team_context.value}\n")
    if request.ui_languages:
        langs = ", ".join(u.value for u in request.ui_languages)
        parts.append(f"- **Idiomas de UI / contenido:** {langs}\n")

    parts.append("\n## Riesgos\n")
    if request.risk_level is not None:
        parts.append(f"- **Nivel de riesgo percibido:** {request.risk_level.value}\n")
    if request.external_dependencies:
        parts.append("- **Dependencias externas críticas:**\n")
        for line in request.external_dependencies:
            parts.append(f"  - {line}\n")

    parts.append("\n## Preferencias de salida\n")
    parts.append(f"- **Profundidad de estimación:** {request.detail_level.value}\n")
    parts.append(f"- **Formato de salida:** {request.output_format.value}\n")

    if request.attachments:
        parts.append("\n## Documentos de apoyo\n")
        parts.extend(line + "\n" for line in _attachment_inline_note(request))

    # Normalize final newline for stable bytes (FR-011)
    text = "".join(parts).strip() + "\n"
    return text


def user_message_template_version() -> str:
    """Version label for logs and documentation."""

    return USER_MESSAGE_TEMPLATE_VERSION
