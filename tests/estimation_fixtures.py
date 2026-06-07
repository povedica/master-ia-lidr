"""Reusable minimal payloads for ``EstimationRequest`` API tests."""

from __future__ import annotations

from typing import Any


def minimal_estimation_request_dict(**overrides: Any) -> dict[str, Any]:
    """Return a JSON-serializable body that satisfies ``EstimationRequest`` validators."""

    base: dict[str, Any] = {
        "project_summary": (
            "B2B partner portal for support intake, SLA tracking, and quarterly reporting."
        ),
        "project_type": "web_saas",
        "target_audience": "b2b_enterprise",
        "project_description": (
            "The client needs a responsive web application for authenticated partners to submit "
            "structured tickets, follow approval workflows, and view status dashboards. "
            "Integrations with existing CRM are out of scope for the first milestone. "
            + "x" * 30
        ),
        "detail_level": "medium",
        "output_format": "phases_table",
        "preprocessing": "none",
        "evaluate": True,
    }
    merged = {**base, **overrides}
    return merged


def out_of_domain_estimation_request_dict() -> dict[str, Any]:
    """Structured payload whose assessment surface should fail the domain guardrail."""

    spam = ("Que distancia hay desde la tierra al sol? " * 12).strip()
    return minimal_estimation_request_dict(
        project_summary=spam[:200],
        project_type="other",
        target_audience="b2c_consumers",
        project_description=spam[:400],
    )
