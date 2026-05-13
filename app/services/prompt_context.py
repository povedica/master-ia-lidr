"""Map ``EstimationRequest`` and mode state into a Jinja-safe context dict."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.context.examples import EstimationExample
from app.context.prompt_loader import load_mode_prompt
from app.schemas.estimation_request import EstimationRequest
from app.services.estimation_engine import EstimationMode


def build_estimation_prompt_context(
    request: EstimationRequest,
    *,
    mode: EstimationMode,
    examples: Sequence[EstimationExample],
    estimation_user_message: str,
    preprocessing: str,
    inline_cleaning_block: str,
    schema_version: str,
) -> dict[str, Any]:
    """Build context for ``app/prompts/estimation/*/`` templates (no raw attachment bytes)."""

    ex_list = [ex.model_dump(mode="json") for ex in examples]
    att_names = [a.filename for a in request.attachments]
    return {
        "mode_system_fragment": load_mode_prompt(mode).strip(),
        "inline_cleaning_block": inline_cleaning_block,
        "examples": ex_list,
        "schema_version": schema_version,
        "detail_level": request.detail_level.value,
        "output_format": request.output_format.value,
        "estimation_user_message": estimation_user_message.strip(),
        "preprocessing": preprocessing,
        "has_attachments": bool(request.attachments),
        "attachment_filenames": att_names,
        "integration_categories": [c.value for c in request.integration_categories],
        "hosting_constraints": [h.value for h in (request.hosting_constraints or [])],
        "ui_languages": [u.value for u in request.ui_languages],
        "delivery_urgency": request.delivery_urgency.value,
        "target_date": request.target_date.isoformat() if request.target_date else None,
    }
