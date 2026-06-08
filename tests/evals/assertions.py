"""Property-based assertions for session estimation eval outcomes."""

from __future__ import annotations

import re
import unicodedata

from app.schemas.estimation_result import EstimationResult
from app.services.sessions import DerivedProjectMetadata
from tests.evals.models import ExpectedMetadataSignals, GoldenSessionCase, SuccessCriteria
from tests.evals.session_runner import SessionEvalOutcome

_COMPONENT_ALIASES: dict[str, tuple[str, ...]] = {
    "authentication": (
        "authentication",
        "auth",
        "login",
        "sso",
        "sign in",
        "signin",
        "identity",
        "access control",
    ),
    "autenticacion": (
        "autenticacion",
        "authentication",
        "auth",
        "login",
        "sso",
        "identity",
    ),
    "dashboard": ("dashboard", "panel", "control panel", "metrics", "executive"),
    "panel": ("panel", "dashboard", "control panel", "metrics"),
    "document": ("document", "pdf", "file upload", "file management", "document sharing", "upload"),
    "redis": ("redis", "cache", "caching", "session token"),
    "react": ("react", "frontend", "spa", "javascript"),
    "cms": ("cms", "content management", "headless cms"),
    "integration": ("integration", "integracion", "api", "erp", "sap", "stripe", "billing"),
    "integracion": ("integracion", "integration", "api", "erp", "sap"),
    "webhook": ("webhook", "webhooks", "callback", "event notification"),
}


def assert_hard_deterministic_outcome(case: GoldenSessionCase, outcome: SessionEvalOutcome) -> None:
    """Run all deterministic property checks for a golden case outcome."""

    estimate = outcome.final_estimate
    _assert_schema_basics(estimate)
    _assert_success_criteria(case.success_criteria, estimate)
    _assert_metadata_signals(case.expected_metadata_signals, outcome.project_metadata)
    _assert_metadata_signals(
        case.success_criteria.expected_metadata_signals or ExpectedMetadataSignals(),
        outcome.project_metadata,
    )


def _assert_schema_basics(estimate: EstimationResult) -> None:
    assert estimate.title.strip()
    assert len(estimate.summary) >= 20
    assert estimate.totals.hours > 0
    assert estimate.duration_weeks > 0
    assert 0.0 <= estimate.confidence <= 1.0
    assert estimate.phases or estimate.line_items
    assert estimate.assumptions
    assert estimate.risks


def _assert_success_criteria(criteria: SuccessCriteria, estimate: EstimationResult) -> None:
    if criteria.expected_hours_range is not None:
        low, high = criteria.expected_hours_range
        assert low <= estimate.totals.hours <= high, (
            f"hours {estimate.totals.hours} outside range [{low}, {high}]"
        )

    if criteria.expected_confidence_band is not None:
        low, high = criteria.expected_confidence_band
        assert low <= estimate.confidence <= high

    for component in criteria.expected_components:
        assert _component_present(component, estimate), f"missing expected component: {component!r}"

    for risk_token in criteria.expected_risks:
        assert _risk_token_present(risk_token, estimate), f"missing expected risk token: {risk_token!r}"

    constraints = criteria.hard_constraints
    if constraints.min_line_items is not None:
        count = len(estimate.line_items) + sum(len(phase.items) for phase in estimate.phases)
        assert count >= constraints.min_line_items, f"expected >= {constraints.min_line_items} line items"

    corpus = _estimate_text_corpus(estimate)
    for forbidden in constraints.must_not_mention:
        assert _normalized_token(forbidden) not in corpus, f"must not mention {forbidden!r}"


def _assert_metadata_signals(
    signals: ExpectedMetadataSignals,
    metadata: DerivedProjectMetadata,
) -> None:
    if signals.project_name is not None:
        assert metadata.project_name == signals.project_name
    if signals.project_type is not None:
        assert str(metadata.project_type) == signals.project_type
    if signals.target_audience is not None:
        assert str(metadata.target_audience) == signals.target_audience
    for token in signals.detected_constraints_contains:
        joined = " ".join(metadata.detected_constraints).lower()
        assert token.lower() in joined, f"constraint token {token!r} not found in metadata"


def _component_aliases(component: str) -> tuple[str, ...]:
    key = _normalized_token(component)
    return _COMPONENT_ALIASES.get(key, (key,))


def _component_present(component: str, estimate: EstimationResult) -> bool:
    corpus = _estimate_text_corpus(estimate)
    return any(_normalized_token(alias) in corpus for alias in _component_aliases(component))


def _risk_token_present(token: str, estimate: EstimationResult) -> bool:
    needle = _normalized_token(token)
    for risk in estimate.risks:
        if needle in _normalized_token(risk):
            return True
    return False


def _line_item_names(estimate: EstimationResult) -> list[str]:
    names = [item.name for item in estimate.line_items]
    for phase in estimate.phases:
        names.extend(item.name for item in phase.items)
    return names


def _estimate_text_corpus(estimate: EstimationResult) -> str:
    parts = [estimate.summary, *estimate.assumptions, *estimate.risks, *_line_item_names(estimate)]
    return _normalized_token(" ".join(parts))


def _normalized_token(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", folded.lower()).strip()
