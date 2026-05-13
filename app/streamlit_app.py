"""Streamlit UI for manual estimation demos (calls FastAPI SSE with structured requests)."""

from __future__ import annotations

import base64
import json
import logging
import os
from collections.abc import Iterator
from datetime import date
from typing import Any

import httpx
import streamlit as st
import streamlit.components.v1 as components
from pydantic import ValidationError

from app.config import get_settings
from app.schemas.estimation_request import (
    DataSensitivity,
    DeliveryApproach,
    DeliveryUrgency,
    DetailLevel,
    EstimationRequest,
    HostingConstraint,
    Industry,
    IntegrationCategory,
    OutputFormat,
    ProjectType,
    RiskLevel,
    TargetAudience,
    TeamContext,
    UiLanguage,
)
from app.services.llm_service import EstimationError
from app.streamlit_error_messages import message_for_estimation_failure

logger = logging.getLogger(__name__)

_PREPROCESSING_OPTIONS: tuple[str, ...] = ("none", "inline_cleaning", "two_phase")
_DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
_STREAM_TIMEOUT_SECONDS = 120.0
_INDUSTRY_NONE = "(none)"


def _scroll_to_top_button() -> None:
    """Inset with JS: Streamlit widgets cannot scroll the app container on their own."""

    components.html(
        """
        <div style="display:flex;justify-content:center;margin:0.5rem 0 0 0;">
          <button type="button" id="btn-volver-arriba-streamlit"
            style="cursor:pointer;padding:0.45rem 1.1rem;border-radius:0.5rem;
                   border:1px solid rgba(49,51,63,0.25);background:rgba(250,250,250,0.95);
                   font-size:0.95rem;font-family:system-ui,sans-serif;">
            Volver arriba
          </button>
        </div>
        <script>
          (function () {
            var b = document.getElementById("btn-volver-arriba-streamlit");
            if (!b) return;
            b.onclick = function () {
              try {
                var doc = window.parent.document;
                var el = doc.querySelector("section.main")
                  || doc.querySelector('[data-testid="stAppViewContainer"]');
                if (el) { el.scrollTo({ top: 0, behavior: "smooth" }); }
                window.parent.scrollTo({ top: 0, behavior: "smooth" });
              } catch (e) {}
            };
          })();
        </script>
        """,
        height=52,
    )


def _format_usage_caption(usage: dict[str, Any]) -> str:
    """Human-readable token line for the last streamed estimation."""

    pt = int(usage.get("prompt_tokens", 0) or 0)
    ct = int(usage.get("completion_tokens", 0) or 0)
    tt = int(usage.get("total_tokens", 0) or 0)
    pin = int(usage.get("preprocessing_input_tokens", 0) or 0)
    pout = int(usage.get("preprocessing_output_tokens", 0) or 0)
    cost = usage.get("estimated_cost_usd")
    parts = [
        f"Prompt tokens: **{pt:,}**",
        f"Completion tokens: **{ct:,}**",
        f"Total: **{tt:,}**",
    ]
    if pin or pout:
        parts.append(f"Preprocessing (in/out): **{pin:,}** / **{pout:,}**")
    if cost is not None:
        parts.append(f"Estimated cost (USD): **{cost}**")
    return " · ".join(parts)


def _non_empty_lines(blob: str, *, max_lines: int | None = None) -> list[str]:
    lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
    if max_lines is not None:
        return lines[:max_lines]
    return lines


def _guess_content_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".md"):
        return "text/markdown"
    return "text/plain"


def _attachments_payload(uploaded: list[Any] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not uploaded:
        return out
    for uf in uploaded[:3]:
        raw = uf.getvalue()
        b64 = base64.b64encode(raw).decode("ascii")
        out.append(
            {
                "filename": uf.name,
                "content_type": _guess_content_type(uf.name),
                "content_base64": b64,
            }
        )
    return out


def _iter_stream_events(
    *,
    request_json: dict[str, Any],
    api_base_url: str,
) -> Iterator[tuple[str, Any]]:
    """Yield ``("chunk", str)``, ``("done", dict)``, or ``("error", str)`` from the SSE stream."""

    url = f"{api_base_url.rstrip('/')}/api/v1/estimate/stream"
    pending_event: str | None = None
    pending_data: list[str] = []

    def flush_event() -> tuple[str, Any] | None:
        nonlocal pending_event, pending_data
        if pending_event is None:
            pending_data.clear()
            return None
        raw_payload = "".join(pending_data).strip()
        pending_data.clear()
        event_name = pending_event
        pending_event = None
        if not raw_payload:
            return None
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise EstimationError("Streaming payload is malformed.") from exc

        if event_name == "chunk":
            return ("chunk", str(payload.get("content", "")))
        if event_name == "done":
            return ("done", payload if isinstance(payload, dict) else {})
        if event_name == "error":
            message = str(payload.get("message", "")).strip() or "Streaming failed."
            return ("error", message)
        return None

    try:
        with httpx.stream(
            "POST",
            url,
            json=request_json,
            timeout=_STREAM_TIMEOUT_SECONDS,
        ) as response:
            if response.status_code >= 400:
                raise EstimationError("Streaming endpoint is unavailable.")
            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line:
                    emitted = flush_event()
                    if emitted is not None:
                        yield emitted
                    continue
                if line.startswith("event:"):
                    pending_event = line.removeprefix("event:").strip()
                    continue
                if line.startswith("data:"):
                    pending_data.append(line.removeprefix("data:").strip())

            emitted = flush_event()
            if emitted is not None:
                yield emitted
    except httpx.ConnectError as exc:
        raise EstimationError(
            "Cannot reach the FastAPI backend (connection refused). "
            "Start it from the repository root with "
            "`uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`, "
            "and ensure the FastAPI base URL matches."
        ) from exc


def _stream_estimation_chunks(
    *,
    request_json: dict[str, Any],
    api_base_url: str,
    done_holder: dict[str, Any],
) -> Iterator[str]:
    """Yield only text deltas for ``st.write_stream``; store the ``done`` payload in ``done_holder``."""

    for kind, payload in _iter_stream_events(
        request_json=request_json,
        api_base_url=api_base_url,
    ):
        if kind == "chunk":
            if payload:
                yield payload
        elif kind == "done":
            done_holder["payload"] = payload
        elif kind == "error":
            raise EstimationError(str(payload))


def main() -> None:
    logging.basicConfig(level=get_settings().log_level.upper(), format="%(levelname)s %(name)s %(message)s")

    st.set_page_config(page_title="Estimador CAG (demo)", layout="centered")

    st.markdown('<div id="top"></div>', unsafe_allow_html=True)
    st.title("Estimador CAG · demo UI")
    st.write(
        "Fill in the guided form (product context). The app streams markdown from "
        "`POST /api/v1/estimate/stream` using the same JSON body as the REST API."
    )

    def _enum_values(enum_cls: type) -> list[str]:
        return [m.value for m in enum_cls]

    project_name = st.text_input("Project name or code (optional)", max_chars=120)
    project_summary = st.text_input(
        "One-line summary",
        help="Required. 20–200 characters after trim.",
    )
    project_type = st.selectbox("Project type", options=_enum_values(ProjectType))
    target_audience = st.selectbox("Target audience", options=_enum_values(TargetAudience))
    target_audience_other = None
    if target_audience == TargetAudience.other.value:
        target_audience_other = st.text_input(
            "Describe the audience (required when “other”)",
            max_chars=200,
        )

    project_description = st.text_area(
        "Project description",
        height=200,
        help="Required narrative (min 100 characters). Add nuance; avoid repeating every select as prose.",
    )

    deliverables_text = st.text_area(
        "Key deliverables (one per line, 3–8 non-empty lines)",
        height=120,
        help="Each line becomes one deliverable (max ~80 characters per line).",
    )

    delivery_urgency = st.selectbox("Delivery urgency", options=_enum_values(DeliveryUrgency))
    target_date: date | None = None
    if delivery_urgency in (
        DeliveryUrgency.fixed_date.value,
        DeliveryUrgency.critical.value,
    ):
        target_date = st.date_input("Target date", value=date.today())

    data_sensitivity = st.selectbox("Data sensitivity", options=_enum_values(DataSensitivity))
    detail_level = st.selectbox("Depth of estimate", options=_enum_values(DetailLevel))
    output_format = st.selectbox("Output format", options=_enum_values(OutputFormat))

    uploaded = st.file_uploader(
        "Supporting documents (optional, max 3)",
        type=["txt", "md", "pdf"],
        accept_multiple_files=True,
        help="Plain text, Markdown, or PDF (PDF body is not OCR’d; see API docs).",
    )

    with st.expander("More details", expanded=False):
        out_of_scope_text = st.text_area(
            "Explicitly out of scope (optional, one per line, max 5)",
            height=80,
        )
        delivery_approach = st.selectbox(
            "Delivery approach (optional)",
            options=["(none)"] + _enum_values(DeliveryApproach),
        )
        integration_categories = st.multiselect(
            "Integration categories (optional)",
            options=_enum_values(IntegrationCategory),
        )
        integration_custom = st.text_area(
            "Custom integration names (optional, one per line, max 3, max 40 chars each)",
            height=60,
        )
        industry_choice = st.selectbox(
            "Industry / domain (optional)",
            options=[_INDUSTRY_NONE] + _enum_values(Industry),
        )
        industry_other = None
        if industry_choice == Industry.other.value:
            industry_other = st.text_input("Industry detail (required when “other”)", max_chars=80)

        hosting_constraints = st.multiselect(
            "Hosting / deployment constraints (optional)",
            options=_enum_values(HostingConstraint),
        )
        hosting_notes = st.text_input("Hosting notes (optional)", max_chars=200)
        team_context = st.selectbox(
            "Team context (optional)",
            options=["(none)"] + _enum_values(TeamContext),
        )
        ui_languages = st.multiselect(
            "UI / content languages (optional, max 3)",
            options=_enum_values(UiLanguage),
            max_selections=3,
        )
        risk_level = st.selectbox(
            "Perceived risk level (optional)",
            options=["(none)"] + _enum_values(RiskLevel),
        )
        external_deps_text = st.text_area(
            "Critical external dependencies (optional, one per line, max 3)",
            height=60,
        )

        preprocessing = st.selectbox(
            "Preprocessing",
            options=list(_PREPROCESSING_OPTIONS),
            help="Same as REST field `preprocessing` (none | inline_cleaning | two_phase).",
        )
        evaluate_like_api = st.checkbox(
            "Structure evaluation (`evaluate`)",
            value=True,
            help="Parity with REST default; does not change SSE chunks.",
        )
        api_base_url = st.text_input(
            "FastAPI base URL",
            value=os.environ.get("ESTIMATOR_API_BASE_URL", _DEFAULT_API_BASE_URL),
            help="Base URL where FastAPI is running (example: http://127.0.0.1:8000).",
        )

    submit = st.button("Generate estimate", type="primary")

    if submit:
        deliverables = _non_empty_lines(deliverables_text)
        out_of_scope = _non_empty_lines(out_of_scope_text, max_lines=5) or None
        integration_custom_names = _non_empty_lines(integration_custom, max_lines=3) or None
        external_dependencies = _non_empty_lines(external_deps_text, max_lines=3) or None

        industry: str | None = None
        if industry_choice != _INDUSTRY_NONE:
            industry = industry_choice

        delivery_appr: str | None = None
        if delivery_approach != "(none)":
            delivery_appr = delivery_approach

        team_ctx: str | None = None
        if team_context != "(none)":
            team_ctx = team_context

        risk: str | None = None
        if risk_level != "(none)":
            risk = risk_level

        raw: dict[str, Any] = {
            "project_name": project_name.strip() or None,
            "project_summary": project_summary,
            "project_type": project_type,
            "target_audience": target_audience,
            "target_audience_other": (target_audience_other or "").strip() or None,
            "industry": industry,
            "industry_other": (industry_other or "").strip() or None,
            "project_description": project_description,
            "deliverables": deliverables,
            "out_of_scope": out_of_scope,
            "delivery_urgency": delivery_urgency,
            "target_date": target_date,
            "delivery_approach": delivery_appr,
            "integration_categories": integration_categories,
            "integration_custom_names": integration_custom_names,
            "data_sensitivity": data_sensitivity,
            "hosting_constraints": hosting_constraints or None,
            "hosting_notes": hosting_notes.strip() or None,
            "team_context": team_ctx,
            "ui_languages": ui_languages,
            "risk_level": risk,
            "external_dependencies": external_dependencies,
            "detail_level": detail_level,
            "output_format": output_format,
            "attachments": _attachments_payload(list(uploaded) if uploaded else []),
            "preprocessing": preprocessing,
            "evaluate": evaluate_like_api,
        }

        try:
            body = EstimationRequest.model_validate(raw)
        except ValidationError as exc:
            st.error("Fix the highlighted fields before submitting.")
            st.json(json.loads(exc.json()))
            return

        request_json = body.model_dump(mode="json")
        try:
            done_meta: dict[str, Any] = {}
            with st.spinner("Streaming estimation…"):
                chunk_stream = _stream_estimation_chunks(
                    request_json=request_json,
                    api_base_url=api_base_url,
                    done_holder=done_meta,
                )
            st.subheader("Estimate")
            st.write_stream(chunk_stream)
            st.caption(f"SSE source: `{api_base_url.rstrip('/')}/api/v1/estimate/stream`")

            done_payload = done_meta.get("payload")
            if isinstance(done_payload, dict):
                usage = done_payload.get("usage")
                if isinstance(usage, dict):
                    st.markdown(_format_usage_caption(usage))
                elif done_payload.get("model"):
                    st.caption(
                        "Token usage was not returned for this run "
                        "(common with non-OpenAI streaming or static fallback). "
                        "Enable `DEV_MODE=true` on the API and use a provider that reports usage."
                    )

            _scroll_to_top_button()
        except EstimationError as exc:
            st.error(message_for_estimation_failure(exc))
        except Exception as exc:
            logger.exception("streamlit_estimate_failed")
            st.error(message_for_estimation_failure(exc))


if __name__ == "__main__":
    main()
