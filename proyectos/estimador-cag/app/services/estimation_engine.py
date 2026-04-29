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
class ModeProfile:
    """Prompt/validation profile associated to each adaptive mode."""

    instruction: str
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


_MODE_PROFILES: dict[EstimationMode, ModeProfile] = {
    EstimationMode.BASIC: ModeProfile(
        instruction=(
            "Return a concise estimate for a small request. Include assumptions, an effort range, "
            "and major risks only."
        ),
        required_sections=("assumption", "estimate", "risk"),
    ),
    EstimationMode.STANDARD: ModeProfile(
        instruction=(
            "Return a practical estimate with assumptions, task breakdown, and effort summary."
        ),
        required_sections=("assumption", "task", "effort"),
    ),
    EstimationMode.PROFESSIONAL: ModeProfile(
        instruction=(
            "Return a detailed estimate with assumptions, dependencies, task breakdown, and "
            "min/realistic/max effort ranges."
        ),
        required_sections=("assumption", "task", "dependencies", "range"),
    ),
    EstimationMode.EXPERT_REVIEW: ModeProfile(
        instruction=(
            "Return an estimation attempt with explicit uncertainty. Highlight missing information "
            "and add recommendation/questions before commitment."
        ),
        required_sections=("assumption", "missing", "uncertainty", "recommendation"),
    ),
}


def get_mode_profile(mode: EstimationMode) -> ModeProfile:
    """Return prompt and lightweight markdown requirements for a mode."""

    return _MODE_PROFILES[mode]


def validate_mode_output(markdown_text: str, mode: EstimationMode) -> bool:
    """Check mode-required keywords in markdown output (v1 lightweight)."""

    normalized = _normalize(markdown_text)
    required_sections = get_mode_profile(mode).required_sections
    return all(section in normalized for section in required_sections)
