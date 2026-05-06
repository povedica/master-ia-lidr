"""Map domain exceptions to user-visible Streamlit strings (no stack traces)."""

from __future__ import annotations

from app.services.llm_service import DomainGuardrailError, EstimationError


def message_for_estimation_failure(exc: BaseException) -> str:
    """Return a short message suitable for Streamlit UI.

    Keeps intentional client-safe wording from estimation errors without echoing raw
    tracebacks or unknown exception details.
    """

    if isinstance(exc, DomainGuardrailError):
        return str(exc)
    if isinstance(exc, EstimationError):
        return str(exc)
    return (
        "Something went wrong while generating the estimate. "
        "If the issue persists, check server logs or environment configuration "
        "(for example `.env` and LLM_PROVIDER settings)."
    )
