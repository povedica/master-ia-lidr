"""Map ``EstimationRequest`` into a Jinja-safe context dict."""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any

from app.context.examples import EstimationExample
from app.schemas.estimation_request import EstimationRequest, Industry, TargetAudience
from app.services.prompt_renderer import PromptRenderer
from app.services.prompt_versions import PromptTemplateSet, resolve_prompt_template_set


def decode_attachment_notes(request: EstimationRequest) -> list[str]:
    """Decode text attachments in Python; PDFs are filename-only notes."""

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


def build_assessment_chunks(request: EstimationRequest) -> list[str]:
    """Narrow assessment surface chunks (no Markdown section headers)."""

    chunks: list[str] = [request.project_summary, request.project_description]
    chunks.extend(request.deliverables)
    if request.out_of_scope:
        chunks.extend(request.out_of_scope)
    return [c.strip() for c in chunks if c and c.strip()]


def _audience_display(request: EstimationRequest) -> str:
    aud = request.target_audience.value
    if request.target_audience == TargetAudience.other and request.target_audience_other:
        return f"{aud} ({request.target_audience_other})"
    return aud


def _industry_display(request: EstimationRequest) -> str | None:
    if request.industry is None:
        return None
    ind = request.industry.value
    if request.industry == Industry.other and request.industry_other:
        return f"{ind} ({request.industry_other})"
    return ind


def build_request_render_context(request: EstimationRequest) -> dict[str, Any]:
    """Context for guided and assessment partials (no few-shot examples)."""

    integration_cats = [c.value for c in request.integration_categories]
    hosting = [h.value for h in (request.hosting_constraints or [])]
    ui_langs = [u.value for u in request.ui_languages]
    return {
        "project_name": request.project_name,
        "project_summary": request.project_summary,
        "project_type": request.project_type.value,
        "target_audience_display": _audience_display(request),
        "industry_display": _industry_display(request),
        "project_description": request.project_description.strip(),
        "deliverables": list(request.deliverables),
        "out_of_scope": list(request.out_of_scope or []),
        "has_out_of_scope": bool(request.out_of_scope),
        "delivery_urgency": request.delivery_urgency.value,
        "target_date": request.target_date.isoformat() if request.target_date else None,
        "delivery_approach": request.delivery_approach.value if request.delivery_approach else None,
        "has_integration_categories": bool(request.integration_categories),
        "integration_categories_display": ", ".join(integration_cats),
        "has_integration_custom_names": bool(request.integration_custom_names),
        "integration_custom_names_display": "; ".join(request.integration_custom_names or []),
        "data_sensitivity": request.data_sensitivity.value,
        "has_hosting_constraints": bool(request.hosting_constraints),
        "hosting_constraints_display": ", ".join(hosting),
        "hosting_notes": request.hosting_notes,
        "team_context": request.team_context.value if request.team_context else None,
        "has_ui_languages": bool(request.ui_languages),
        "ui_languages_display": ", ".join(ui_langs),
        "risk_level": request.risk_level.value if request.risk_level else None,
        "external_dependencies": list(request.external_dependencies or []),
        "has_external_dependencies": bool(request.external_dependencies),
        "detail_level": request.detail_level.value,
        "output_format": request.output_format.value,
        "has_attachments": bool(request.attachments),
        "attachment_notes": decode_attachment_notes(request),
        "assessment_chunks": build_assessment_chunks(request),
    }


def build_prompt_render_context(
    request: EstimationRequest,
    *,
    template_set: PromptTemplateSet,
    examples: Sequence[EstimationExample],
    estimation_user_message: str,
    preprocessing: str,
    inline_cleaning_block: str,
    schema_version: str,
    use_preprocessed_user_message: bool,
    renderer: PromptRenderer | None = None,
) -> dict[str, Any]:
    """Build full context for estimation system/user/examples templates."""

    r = renderer or PromptRenderer()
    ctx = build_request_render_context(request)
    ex_list = [ex.model_dump(mode="json") for ex in examples]
    ctx.update(
        {
            "system_instructions_template": template_set.system_instructions_template,
            "inline_cleaning_block": inline_cleaning_block,
            "examples": ex_list,
            "schema_version": schema_version,
            "estimation_user_message": estimation_user_message.strip(),
            "preprocessing": preprocessing,
            "use_preprocessed_user_message": use_preprocessed_user_message,
            "guided_request_template": template_set.guided_request_template,
            "structured_output_hint_template": template_set.structured_output_hint_template,
            "attachment_filenames": [a.filename for a in request.attachments],
            "integration_categories": [c.value for c in request.integration_categories],
            "hosting_constraints": [h.value for h in (request.hosting_constraints or [])],
            "ui_languages": [u.value for u in request.ui_languages],
        }
    )
    return ctx


def build_estimation_prompt_context(
    request: EstimationRequest,
    *,
    examples: Sequence[EstimationExample],
    estimation_user_message: str,
    preprocessing: str,
    inline_cleaning_block: str,
    schema_version: str,
    version: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper; resolves bundle and builds full render context."""

    template_set = resolve_prompt_template_set("estimation", version)
    use_preprocessed = (
        preprocessing == "two_phase"
        and bool(estimation_user_message.strip())
    )
    return build_prompt_render_context(
        request,
        template_set=template_set,
        examples=examples,
        estimation_user_message=estimation_user_message,
        preprocessing=preprocessing,
        inline_cleaning_block=inline_cleaning_block,
        schema_version=schema_version,
        use_preprocessed_user_message=use_preprocessed,
    )
