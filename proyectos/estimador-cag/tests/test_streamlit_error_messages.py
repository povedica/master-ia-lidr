"""Tests for Streamlit-facing error summaries."""

from app.services.llm_service import DomainGuardrailError, EstimationError
from app.streamlit_error_messages import message_for_estimation_failure


def test_domain_guardrail_uses_exception_message() -> None:
    exc = DomainGuardrailError("Only software/project estimation requests are supported.")
    assert message_for_estimation_failure(exc) == str(exc)


def test_estimation_error_uses_exception_message() -> None:
    exc = EstimationError("All providers failed.")
    assert message_for_estimation_failure(exc) == str(exc)


def test_unknown_exception_is_generic_message() -> None:
    msg = message_for_estimation_failure(RuntimeError("internal secret xyz"))
    assert "internal secret xyz" not in msg
    assert "Something went wrong" in msg
