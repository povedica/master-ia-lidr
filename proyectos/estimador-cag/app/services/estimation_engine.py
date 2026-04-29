"""Deterministic adaptive estimation helpers and lightweight validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)

_DETAIL_SIGNALS = (
    "api",
    "backend",
    "frontend",
    "database",
    "sso",
    "csv",
    "integration",
    "auth",
    "dashboard",
    "admin",
    "migration",
    "testing",
    "login",
    "form",
    "page",
    "portal",
    "website",
)

_COMPLETENESS_SIGNALS = (
    "scope",
    "deliverable",
    "deadline",
    "budget",
    "requirement",
    "constraint",
    "acceptance",
    "timeline",
)

_AMBIGUITY_SIGNALS = (
    "maybe",
    "not sure",
    "unclear",
    "something like",
    "etc",
    "whatever",
    "algun",
    "alguna",
    "no se",
    "depende",
)


class EstimationMode(StrEnum):
    """Supported output granularity levels for adaptive estimation."""

    BASIC = "basic"
    STANDARD = "standard"
    PROFESSIONAL = "professional"
    EXPERT_REVIEW = "expert_review"


@dataclass(frozen=True)
class RequestAssessment:
    """Deterministic scoring outcome used for mode routing."""

    detail_score: int
    completeness_score: int
    ambiguity_score: int
    word_count: int


@dataclass(frozen=True)
class InputAssessment:
    """Machine-readable summary of input quality and routing decision."""

    detail_level: str
    recommended_mode: EstimationMode
    reason: str


@dataclass(frozen=True)
class ModeEligibility:
    """Business guardrail decision for allowed and blocked modes."""

    allowed_modes: tuple[EstimationMode, ...]
    blocked_modes: tuple[EstimationMode, ...]
    reason: str | None


@dataclass(frozen=True)
class ModeProfile:
    """Validation profile associated to each adaptive mode."""

    required_sections: tuple[str, ...]


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def _score_signals(text: str, signals: tuple[str, ...]) -> int:
    return sum(1 for signal in signals if signal in text)


def assess_request(transcription: str) -> RequestAssessment:
    """Assess detail/completeness/ambiguity from raw user text."""

    normalized = _normalize(transcription)
    words = normalized.split()
    detail = _score_signals(normalized, _DETAIL_SIGNALS)
    completeness = _score_signals(normalized, _COMPLETENESS_SIGNALS)
    ambiguity = _score_signals(normalized, _AMBIGUITY_SIGNALS)
    return RequestAssessment(
        detail_score=detail,
        completeness_score=completeness,
        ambiguity_score=ambiguity,
        word_count=len(words),
    )


def select_mode(assessment: RequestAssessment) -> EstimationMode:
    """Map request assessment scores to one adaptive mode."""

    if assessment.ambiguity_score > 0:
        return EstimationMode.EXPERT_REVIEW

    if (
        assessment.word_count >= 28
        and assessment.detail_score >= 5
        and assessment.completeness_score >= 1
    ):
        return EstimationMode.PROFESSIONAL

    if assessment.word_count <= 18 and assessment.detail_score >= 1:
        return EstimationMode.BASIC

    return EstimationMode.STANDARD


def assess_and_select_mode(transcription: str) -> tuple[RequestAssessment, EstimationMode]:
    """Convenience helper that performs assessment and routing together."""

    assessment = assess_request(transcription)
    return assessment, select_mode(assessment)


def summarize_assessment(
    assessment: RequestAssessment,
    recommended_mode: EstimationMode,
) -> InputAssessment:
    """Build public assessment summary from deterministic scoring signals."""

    if assessment.ambiguity_score > 0:
        reason = (
            "The input has ambiguity markers and missing constraints. "
            "An expert review mode is safer to expose uncertainty and gaps."
        )
    elif recommended_mode == EstimationMode.PROFESSIONAL:
        reason = (
            "The input includes rich technical context and scope constraints, "
            "which supports a defendable professional estimation."
        )
    elif recommended_mode == EstimationMode.BASIC:
        reason = (
            "The input is short with limited planning context, so a quick basic "
            "estimate is more appropriate than deep planning detail."
        )
    else:
        reason = (
            "The input provides useful functional context but lacks full delivery "
            "constraints, so standard mode offers balanced detail and uncertainty."
        )

    if assessment.ambiguity_score > 0:
        detail_level = "low"
    elif assessment.detail_score >= 6 and assessment.completeness_score >= 2:
        detail_level = "expert"
    elif assessment.detail_score >= 4 and assessment.completeness_score >= 1:
        detail_level = "high"
    elif assessment.detail_score >= 2:
        detail_level = "medium"
    else:
        detail_level = "low"

    return InputAssessment(
        detail_level=detail_level,
        recommended_mode=recommended_mode,
        reason=reason,
    )


def evaluate_mode_eligibility(summary: InputAssessment) -> ModeEligibility:
    """Apply business guardrail to block premium modes on weak context."""

    all_modes = (
        EstimationMode.BASIC,
        EstimationMode.STANDARD,
        EstimationMode.PROFESSIONAL,
        EstimationMode.EXPERT_REVIEW,
    )
    if summary.detail_level in {"high", "expert"}:
        return ModeEligibility(
            allowed_modes=all_modes,
            blocked_modes=(),
            reason=None,
        )

    return ModeEligibility(
        allowed_modes=(EstimationMode.BASIC, EstimationMode.STANDARD),
        blocked_modes=(EstimationMode.PROFESSIONAL, EstimationMode.EXPERT_REVIEW),
        reason="Input detail is insufficient.",
    )


def enforce_mode_eligibility(
    recommended_mode: EstimationMode,
    eligibility: ModeEligibility,
) -> EstimationMode:
    """Return the mode actually allowed by business guardrail."""

    if recommended_mode in eligibility.allowed_modes:
        return recommended_mode
    if EstimationMode.STANDARD in eligibility.allowed_modes:
        return EstimationMode.STANDARD
    return eligibility.allowed_modes[0]


_MODE_PROFILES: dict[EstimationMode, ModeProfile] = {
    EstimationMode.BASIC: ModeProfile(required_sections=("assumption", "estimate", "risk")),
    EstimationMode.STANDARD: ModeProfile(required_sections=("assumption", "task", "effort")),
    EstimationMode.PROFESSIONAL: ModeProfile(
        required_sections=("assumption", "task", "dependencies", "range"),
    ),
    EstimationMode.EXPERT_REVIEW: ModeProfile(
        required_sections=("assumption", "missing", "uncertainty", "recommendation"),
    ),
}


def get_mode_profile(mode: EstimationMode) -> ModeProfile:
    """Return lightweight markdown requirements for a mode."""

    return _MODE_PROFILES[mode]


def validate_mode_output(markdown_text: str, mode: EstimationMode) -> bool:
    """Check mode-required keywords in markdown output (v1 lightweight)."""

    normalized = _normalize(markdown_text)
    required_sections = get_mode_profile(mode).required_sections
    return all(section in normalized for section in required_sections)
