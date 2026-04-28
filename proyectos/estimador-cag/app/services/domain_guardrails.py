"""Deterministic domain guardrails for estimation requests."""

from __future__ import annotations

from dataclasses import dataclass
import re


_SOFTWARE_SIGNALS = (
    "api",
    "frontend",
    "backend",
    "dashboard",
    "portal",
    "landing page",
    "mobile app",
    "mvp",
    "integration",
    "database",
    "auth",
    "admin panel",
    "feature",
    "bug",
    "migration",
    "funcionalidad",
    "proyecto",
    "aplicacion",
    "aplicación",
    "web",
    "panel",
    "integracion",
    "integración",
    "software",
)

_ESTIMATION_SIGNALS = (
    "estimate",
    "estimation",
    "hours",
    "timeline",
    "scope",
    "tasks",
    "delivery",
    "budget",
    "estimar",
    "estimacion",
    "estimación",
    "horas",
    "plazos",
    "tareas",
    "entrega",
    "presupuesto",
)

_GENERAL_QUESTION_STARTS = (
    "que ",
    "qué ",
    "quien ",
    "quién ",
    "por que",
    "por qué",
    "what is",
    "who is",
    "how far is",
)

_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


@dataclass(frozen=True)
class DomainCheckResult:
    """Decision emitted by the domain guardrail helper."""

    accepted: bool
    reason: str | None = None


def _normalize_text(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def _contains_any_signal(text: str, signals: tuple[str, ...]) -> bool:
    return any(signal in text for signal in signals)


def _starts_like_general_question(text: str) -> bool:
    return any(text.startswith(pattern) for pattern in _GENERAL_QUESTION_STARTS)


def check_estimation_domain(text: str) -> DomainCheckResult:
    """Accept requests that look like software/project estimation work."""

    normalized = _normalize_text(text)
    if not normalized:
        return DomainCheckResult(accepted=False, reason="empty_after_normalization")

    has_software_signal = _contains_any_signal(normalized, _SOFTWARE_SIGNALS)
    has_estimation_signal = _contains_any_signal(normalized, _ESTIMATION_SIGNALS)

    if has_software_signal:
        return DomainCheckResult(accepted=True)

    word_count = len(normalized.split())
    has_general_question_shape = _starts_like_general_question(normalized)

    if has_general_question_shape and not has_estimation_signal:
        return DomainCheckResult(accepted=False, reason="general_question_no_domain_signal")

    if word_count < 20 and not has_estimation_signal:
        return DomainCheckResult(accepted=False, reason="short_text_no_domain_signal")

    if has_estimation_signal:
        return DomainCheckResult(accepted=True)

    return DomainCheckResult(accepted=False, reason="no_domain_signal")
