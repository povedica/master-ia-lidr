"""Minimal Streamlit UI for manual estimation demos (delegates to EstimationService)."""

from __future__ import annotations

import asyncio
import logging

import streamlit as st

from app.config import get_settings
from app.services.llm_service import DomainGuardrailError, EstimationError, EstimationService
from app.services.providers import build_provider_chain
from app.streamlit_error_messages import message_for_estimation_failure

logger = logging.getLogger(__name__)

_PREPROCESSING_OPTIONS: tuple[str, ...] = ("none", "inline_cleaning", "two_phase")


def _estimation_service() -> EstimationService:
    settings = get_settings()
    return EstimationService(settings, build_provider_chain(settings))


def _estimate_sync(transcription: str, preprocessing: str):
    async def runner():
        service = _estimation_service()
        return await service.estimate(transcription, preprocessing=preprocessing)

    return asyncio.run(runner())


def main() -> None:
    logging.basicConfig(level=get_settings().log_level.upper(), format="%(levelname)s %(name)s %(message)s")

    st.set_page_config(page_title="Estimador CAG (demo)", layout="centered")

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

    submit = st.button("Generate estimate", type="primary")

    if submit:
        text = transcription.strip()
        if not text:
            st.error("Enter a transcription before generating an estimate.")
        else:
            try:
                with st.spinner("Running estimation pipeline…"):
                    result = _estimate_sync(text, preprocessing)
                st.subheader("Estimate")
                st.markdown(result.estimation)
                meta = (
                    f"**Mode:** `{result.mode.value}` · **Provider:** `{result.provider}` · "
                    f"**Model:** `{result.model}`"
                )
                if result.degraded:
                    meta += " · **Degraded:** static fallback was used."
                st.caption(meta)
            except DomainGuardrailError as exc:
                st.error(message_for_estimation_failure(exc))
            except EstimationError as exc:
                st.error(message_for_estimation_failure(exc))
            except Exception as exc:
                logger.exception("streamlit_estimate_failed")
                st.error(message_for_estimation_failure(exc))


if __name__ == "__main__":
    main()
