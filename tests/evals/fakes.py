"""Golden-aligned structured LLM fake for deterministic eval runs."""

from __future__ import annotations

import unicodedata

from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from tests.evals.models import SuccessCriteria
from tests.fakes.fake_llm_provider import FakeStructuredLLM

_HOUR_RATE_EUR = 50.0


class EvalStructuredLLM(FakeStructuredLLM):
    """Returns ``EstimationResult`` payloads aligned with golden success criteria."""

    def __init__(self) -> None:
        super().__init__()
        self._criteria: SuccessCriteria | None = None

    def set_success_criteria(self, criteria: SuccessCriteria) -> None:
        self._criteria = criteria

    def clear_success_criteria(self) -> None:
        self._criteria = None

    def _dispatch(self, user_prompt: str) -> EstimationResult:
        if self._criteria is not None:
            return build_estimation_from_criteria(self._criteria, user_prompt=user_prompt)
        return super()._dispatch(user_prompt)


def build_estimation_from_criteria(
    criteria: SuccessCriteria,
    *,
    user_prompt: str = "",
) -> EstimationResult:
    """Build a valid structured estimate that satisfies golden property checks."""

    del user_prompt
    hours = _pick_hours(criteria)
    components = _pick_components(criteria)
    line_items = [
        EstimationLineItem(
            name=_title_case_component(name),
            hours=max(hours / len(components), 1.0),
            cost_eur=max(hours / len(components), 1.0) * _HOUR_RATE_EUR,
        )
        for name in components
    ]
    totals = EstimationTotals(hours=sum(item.hours for item in line_items), cost_eur=sum(item.cost_eur for item in line_items))
    confidence = _pick_confidence(criteria)
    risks = _build_risks(criteria)
    assumptions = [
        "Scope derived from multi-turn session context and accumulated metadata.",
        "Estimates assume standard team velocity and no major scope churn.",
    ]
    return EstimationResult(
        title="Session evaluation estimate",
        summary=(
            "Structured estimate covering the agreed session scope with phased delivery, "
            "explicit assumptions, and identified integration risks."
        ),
        phases=[],
        line_items=line_items,
        totals=totals,
        duration_weeks=max(totals.hours / 40.0, 1.0),
        confidence=confidence,
        assumptions=assumptions,
        risks=risks,
    )


def _pick_hours(criteria: SuccessCriteria) -> float:
    if criteria.expected_hours_range is not None:
        low, high = criteria.expected_hours_range
        return (low + high) / 2.0
    return 80.0


def _pick_confidence(criteria: SuccessCriteria) -> float:
    if criteria.expected_confidence_band is not None:
        low, high = criteria.expected_confidence_band
        return (low + high) / 2.0
    return 0.75


def _pick_components(criteria: SuccessCriteria) -> list[str]:
    min_items = criteria.hard_constraints.min_line_items or 3
    components = list(criteria.expected_components)
    while len(components) < min_items:
        components.append(f"core-workstream-{len(components) + 1}")
    return components[: max(min_items, len(components))]


def _build_risks(criteria: SuccessCriteria) -> list[str]:
    risks: list[str] = []
    for token in criteria.expected_risks:
        risks.append(f"Risk: {token} uncertainty may affect timeline and integration effort.")
    if not risks:
        risks.append("Risk: scope ambiguity may require additional discovery.")
    return risks


def _title_case_component(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return normalized.replace("_", " ").strip().title() or name.title()
