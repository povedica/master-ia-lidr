"""Minimal Streamlit UI for manual estimation demos (delegates to EstimationService)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components

from app.config import get_settings
from app.services.estimate_response_builder import assemble_estimate_response, dev_response_property_rows
from app.services.llm_service import DomainGuardrailError, EstimationError, EstimationService
from app.services.llm_chain import build_provider_chain
from app.streamlit_error_messages import message_for_estimation_failure

logger = logging.getLogger(__name__)

_PREPROCESSING_OPTIONS: tuple[str, ...] = ("none", "inline_cleaning", "two_phase")


def _estimation_service() -> EstimationService:
    settings = get_settings()
    return EstimationService(settings, build_provider_chain(settings))


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


def _estimate_sync(transcription: str, preprocessing: str):
    async def runner():
        service = _estimation_service()
        return await service.estimate(transcription, preprocessing=preprocessing)

    return asyncio.run(runner())


def main() -> None:
    logging.basicConfig(level=get_settings().log_level.upper(), format="%(levelname)s %(name)s %(message)s")

    st.set_page_config(page_title="Estimador CAG (demo)", layout="centered")

    st.markdown('<div id="top"></div>', unsafe_allow_html=True)
    st.title("Estimador CAG · demo UI")
    st.write(
        "Enter a meeting transcription describing software work to estimate. "
        "Responses are produced via the same `EstimationService` as the REST API—not by calling "
        "providers from this UI."
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

    submit = st.button("Generate estimate", type="primary")

    if submit:
        text = transcription.strip()
        if not text:
            st.error("Enter a transcription before generating an estimate.")
        else:
            try:
                settings = get_settings()
                request_id = f"est_{uuid4().hex[:12]}"
                start_perf = perf_counter()
                with st.spinner("Running estimation pipeline…"):
                    result = _estimate_sync(text, preprocessing)
                finished_at = datetime.now(UTC)
                latency_ms = int((perf_counter() - start_perf) * 1000)

                api_shaped, _ = assemble_estimate_response(
                    result,
                    evaluate=evaluate_like_api,
                    dev_mode=settings.dev_mode,
                    stats_log_enabled=False,
                    request_id=request_id,
                    finished_at=finished_at,
                    latency_ms=latency_ms,
                )

                st.subheader("Estimate")
                st.markdown(result.estimation)
                meta = (
                    f"**Mode:** `{result.mode.value}` · **Provider:** `{result.provider}` · "
                    f"**Model:** `{result.model}`"
                )
                if result.degraded:
                    meta += " · **Degraded:** static fallback was used."
                st.caption(meta)

                if settings.dev_mode:
                    dev_rows = dev_response_property_rows(api_shaped)
                    st.subheader("Campos JSON (DEV_MODE)")
                    st.caption(
                        "Misma forma que `POST /api/v1/estimate` con `DEV_MODE=true`. "
                        "Los campos omitidos cuando son `null` no aparecen en la tabla."
                    )
                    st.dataframe(
                        dev_rows,
                        use_container_width=True,
                        hide_index=True,
                        height=min(920, max(260, len(dev_rows) * 38)),
                        column_config={
                            "field": st.column_config.TextColumn("Campo"),
                            "value": st.column_config.TextColumn("Valor"),
                        },
                    )

                _scroll_to_top_button()
            except DomainGuardrailError as exc:
                st.error(message_for_estimation_failure(exc))
            except EstimationError as exc:
                st.error(message_for_estimation_failure(exc))
            except Exception as exc:
                logger.exception("streamlit_estimate_failed")
                st.error(message_for_estimation_failure(exc))


if __name__ == "__main__":
    main()
