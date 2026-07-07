"""Optional transcript PII redaction (feature-065)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol


class PiiAnalyzer(Protocol):
    def analyze(self, text: str) -> list[tuple[int, int, str]]: ...


@dataclass(frozen=True)
class RedactedTranscript:
    text: str
    entities_redacted: int = 0
    entity_types: list[str] = field(default_factory=list)


def _default_redact_spans(text: str, spans: list[tuple[int, int, str]]) -> RedactedTranscript:
    if not spans:
        return RedactedTranscript(text=text)
    ordered = sorted(spans, key=lambda item: item[0], reverse=True)
    redacted = text
    types: set[str] = set()
    for start, end, entity_type in ordered:
        token = f"<{entity_type}>"
        redacted = redacted[:start] + token + redacted[end:]
        types.add(entity_type)
    return RedactedTranscript(
        text=redacted,
        entities_redacted=len(spans),
        entity_types=sorted(types),
    )


def redact_transcript(
    text: str,
    *,
    enabled: bool,
    analyzer: PiiAnalyzer | None = None,
) -> RedactedTranscript:
    if not enabled:
        return RedactedTranscript(text=text)
    if analyzer is None:
        return RedactedTranscript(text=text)
    spans = analyzer.analyze(text)
    return _default_redact_spans(text, spans)


class RegexPiiAnalyzer:
    """Lightweight analyzer for tests and dev without Presidio installed."""

    def __init__(self, patterns: dict[str, str] | None = None) -> None:
        import re

        self._patterns = patterns or {
            "EMAIL_ADDRESS": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            "PHONE_NUMBER": r"\b\+?\d[\d\s\-()]{7,}\d\b",
        }
        self._compiled = {name: re.compile(pattern) for name, pattern in self._patterns.items()}

    def analyze(self, text: str) -> list[tuple[int, int, str]]:
        spans: list[tuple[int, int, str]] = []
        for entity_type, pattern in self._compiled.items():
            for match in pattern.finditer(text):
                spans.append((match.start(), match.end(), entity_type))
        return spans


def build_presidio_analyzer(entity_types: list[str], language: str) -> Callable[[], PiiAnalyzer]:
    def _factory() -> PiiAnalyzer:
        from presidio_analyzer import AnalyzerEngine

        engine = AnalyzerEngine()
        entity_list = entity_types

        class _PresidioAdapter:
            def analyze(self, text: str) -> list[tuple[int, int, str]]:
                results = engine.analyze(text=text, language=language, entities=entity_list)
                return [(item.start, item.end, item.entity_type) for item in results]

        return _PresidioAdapter()

    return _factory
