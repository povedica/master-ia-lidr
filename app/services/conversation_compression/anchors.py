"""Heuristic anchor detection for session compression (feature-064)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_HEURISTIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("nda", re.compile(r"\b(nda|non[- ]?disclosure|under embargo|legal hold)\b", re.IGNORECASE)),
    (
        "signed_contract",
        re.compile(
            r"\b(signed|countersigned)\s+(the\s+)?(contract|sow|msa|agreement)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "scope_frozen",
        re.compile(r"\b(scope|backlog)\s+(is\s+)?(frozen|locked|final|fixed)\b", re.IGNORECASE),
    ),
    (
        "budget_locked",
        re.compile(
            r"\b(budget|cap|ceiling)\s+(is\s+)?(locked|fixed|approved|capped)\s+at\b",
            re.IGNORECASE,
        ),
    ),
    ("compliance", re.compile(r"\b(hipaa|gdpr|sox|pci[- ]?dss|fda|iso[- ]?27001)\b", re.IGNORECASE)),
    ("deadline_hard", re.compile(r"\bhard\s+deadline\b|\bmust\s+go\s+live\s+by\b", re.IGNORECASE)),
    ("explicit_commitment", re.compile(r"\b(we|the (client|customer))\s+(agreed|committed)\s+to\b", re.IGNORECASE)),
)


@dataclass
class AnchorMatch:
    is_anchor: bool
    matched_rules: list[str] = field(default_factory=list)


class AnchorDetector:
    def __init__(self, *, mode: str = "heuristic") -> None:
        self._mode = mode

    def detect(self, user_text: str) -> AnchorMatch:
        if self._mode != "heuristic":
            return AnchorMatch(is_anchor=False)
        matched = [
            rule_name
            for rule_name, pattern in _HEURISTIC_PATTERNS
            if pattern.search(user_text)
        ]
        return AnchorMatch(is_anchor=bool(matched), matched_rules=matched)
