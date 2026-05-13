"""Domain guardrail tests for estimation classification."""

from app.services.domain_guardrails import check_estimation_domain


def test_accepts_clear_software_request() -> None:
    result = check_estimation_domain(
        "Client needs a landing page with HubSpot integration and admin panel."
    )
    assert result.accepted is True


def test_accepts_spanish_software_request() -> None:
    result = check_estimation_domain(
        "Necesitamos estimar el desarrollo de un panel de admin con login."
    )
    assert result.accepted is True


def test_accepts_short_spanish_estimation_request() -> None:
    result = check_estimation_domain("Quiero hacer un formulario de login. Estimalo.")
    assert result.accepted is True


def test_rejects_general_knowledge_question() -> None:
    result = check_estimation_domain("Que distancia hay desde la tierra al sol?")
    assert result.accepted is False
    assert result.reason == "general_question_no_domain_signal"


def test_rejects_short_unrelated_message() -> None:
    result = check_estimation_domain("Hola, que tal?")
    assert result.accepted is False
    assert result.reason == "short_text_no_domain_signal"
