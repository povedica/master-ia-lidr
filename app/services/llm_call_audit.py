"""Request-scoped audit context for LLM call JSON persistence."""

from __future__ import annotations

import base64
import binascii
import json
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

from app.services.prompt_renderer import RenderedPrompt
from app.services.prompt_versions import PromptTemplateSet
from app.services.prompt_renderer import RenderedPrompt

_audit_state: ContextVar[dict[str, Any] | None] = ContextVar("llm_call_audit_state", default=None)


def _empty_state() -> dict[str, Any]:
    return {
        "api_endpoint": None,
        "variables_before_render": None,
        "templates": None,
        "prompt_overrides": None,
        "notes": [],
    }


def reset_llm_call_audit() -> Token[dict[str, Any] | None]:
    """Clear audit state; returns a token for optional restore."""

    return _audit_state.set(_empty_state())


def restore_llm_call_audit(token: Token[dict[str, Any] | None]) -> None:
    """Restore audit state from a prior ``reset_llm_call_audit`` token."""

    _audit_state.reset(token)


def set_llm_call_api_endpoint(*, method: str, path: str, request_id: str | None = None) -> None:
    """Record the HTTP route that triggered the current LLM work."""

    state = _audit_state.get()
    if state is None:
        state = _empty_state()
        _audit_state.set(state)
    state["api_endpoint"] = {"method": method.upper(), "path": path}
    if request_id:
        state["request_id"] = request_id


def merge_llm_call_audit(**fields: Any) -> None:
    """Merge optional preparation fields into the current audit state."""

    state = _audit_state.get()
    if state is None:
        state = _empty_state()
        _audit_state.set(state)
    for key, value in fields.items():
        if key == "notes" and isinstance(value, list):
            notes = state.setdefault("notes", [])
            if isinstance(notes, list):
                notes.extend(value)
            continue
        state[key] = value


def template_set_to_audit_dict(template_set: PromptTemplateSet) -> dict[str, str]:
    """Serialize manifest template paths for persistence."""

    return {
        "use_case": template_set.use_case,
        "bundle_version": template_set.version,
        "system_template": template_set.system_template,
        "user_template": template_set.user_template,
        "examples_template": template_set.examples_template,
        "guided_request_template": template_set.guided_request_template,
        "system_instructions_template": template_set.system_instructions_template,
        "assessment_surface_template": template_set.assessment_surface_template,
        "structured_output_hint_template": template_set.structured_output_hint_template,
        "inline_cleaning_template": template_set.inline_cleaning_template,
        "two_phase_extraction_system_template": template_set.two_phase_extraction_system_template,
    }


def record_prompt_render_audit(
    *,
    template_set: PromptTemplateSet,
    variables_before_render: dict[str, Any],
    rendered: RenderedPrompt | None = None,
    examples_version: str | None = None,
) -> None:
    """Capture Jinja context and template manifest before the provider call."""

    templates: dict[str, Any] = {
        "manifest": template_set_to_audit_dict(template_set),
    }
    if rendered is not None:
        templates["prompt_version"] = rendered.prompt_version
        templates["rendered_template_names"] = list(rendered.template_names)
    if examples_version is not None:
        templates["examples_version"] = examples_version
    merge_llm_call_audit(
        templates=templates,
        variables_before_render=sanitize_variables_for_persistence(variables_before_render),
    )


def record_structured_call_overrides(
    *,
    system_prompt_override: str | None = None,
    user_prompt_override: str | None = None,
    messages_override: list[dict[str, str]] | None = None,
) -> None:
    """Record whether rendered prompts were replaced before ``complete_structured``."""

    merge_llm_call_audit(
        prompt_overrides={
            "system_prompt_override": system_prompt_override is not None,
            "user_prompt_override": user_prompt_override is not None,
            "messages_override": messages_override is not None,
            "messages_override_count": len(messages_override) if messages_override else 0,
        }
    )


def record_v1_system_prompt_audit(
    *,
    template_set: PromptTemplateSet,
    detail_level: str,
    output_format: str,
    inline_cleaning: bool,
    examples_version: str,
) -> None:
    """Capture v1 markdown path system prompt variables (hardcoded depth/format)."""

    variables = {
        "detail_level": detail_level,
        "output_format": output_format,
        "inline_cleaning": inline_cleaning,
    }
    record_prompt_render_audit(
        template_set=template_set,
        variables_before_render=variables,
        examples_version=examples_version,
    )
    merge_llm_call_audit(notes=["v1_markdown_estimation_path"])


def snapshot_llm_call_preparation() -> dict[str, Any]:
    """Return a JSON-safe copy of the current preparation snapshot."""

    state = _audit_state.get()
    if state is None:
        return {}
    return json.loads(json.dumps(state, ensure_ascii=False, default=str))


def sanitize_variables_for_persistence(ctx: dict[str, Any]) -> dict[str, Any]:
    """Make Jinja context JSON-safe; redact secrets and heavy binary payloads."""

    return _sanitize_value(ctx)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        if _looks_like_base64_blob(value):
            return f"<base64 omitted, {len(value)} chars>"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _looks_like_base64_blob(text: str) -> bool:
    stripped = "".join(text.split())
    if len(stripped) < 256:
        return False
    try:
        base64.b64decode(stripped, validate=True)
    except (ValueError, binascii.Error):
        return False
    return True
