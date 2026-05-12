"""Minimal Streamlit UI for manual estimation demos (delegates to EstimationService)."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from typing import Any

import httpx
import streamlit as st
import streamlit.components.v1 as components

from app.config import get_settings
from app.services.llm_service import EstimationError
from app.streamlit_error_messages import message_for_estimation_failure

logger = logging.getLogger(__name__)

_PREPROCESSING_OPTIONS: tuple[str, ...] = ("none", "inline_cleaning", "two_phase")
_DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
_STREAM_TIMEOUT_SECONDS = 120.0


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


def _iter_stream_events(
    *,
    transcription: str,
    preprocessing: str,
    evaluate: bool,
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
            json={
                "transcription": transcription,
                "preprocessing": preprocessing,
                "evaluate": evaluate,
            },
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
            "Start it from proyectos/estimador-cag with "
            "`uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`, "
            "and ensure the FastAPI base URL matches."
        ) from exc


def _stream_estimation_chunks(
    *,
    transcription: str,
    preprocessing: str,
    evaluate: bool,
    api_base_url: str,
    done_holder: dict[str, Any],
) -> Iterator[str]:
    """Yield only text deltas for ``st.write_stream``; store the ``done`` payload in ``done_holder``."""

    for kind, payload in _iter_stream_events(
        transcription=transcription,
        preprocessing=preprocessing,
        evaluate=evaluate,
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
        "Enter a meeting transcription describing software work to estimate. "
        "Responses are consumed progressively from the FastAPI SSE endpoint."
    )

    transcription = st.text_area(
        "Transcription",
        height=260,
        placeholder="Paste meeting notes or functional requirements relevant to software estimation…",
        label_visibility="visible",
    )

    preprocessing = st.selectbox(
        "Preprocessing",
        options=list(_PREPROCESSING_OPTIONS),
        help="Same choices as REST body field `preprocessing` (none | inline_cleaning | two_phase).",
    )

    evaluate_like_api = st.checkbox(
        "Structure evaluation (`evaluate`)",
        value=True,
        help="Matches REST default: when enabled, responses include score, structure_evaluation, and output_validation when applicable.",
    )
    api_base_url = st.text_input(
        "FastAPI base URL",
        value=os.environ.get("ESTIMATOR_API_BASE_URL", _DEFAULT_API_BASE_URL),
        help="Base URL where FastAPI is running (example: http://127.0.0.1:8000).",
    )

    submit = st.button("Generate estimate", type="primary")

    if submit:
        text = transcription.strip()
        if not text:
            st.error("Enter a transcription before generating an estimate.")
        else:
            try:
                done_meta: dict[str, Any] = {}
                with st.spinner("Streaming estimation…"):
                    chunk_stream = _stream_estimation_chunks(
                        transcription=text,
                        preprocessing=preprocessing,
                        evaluate=evaluate_like_api,
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
