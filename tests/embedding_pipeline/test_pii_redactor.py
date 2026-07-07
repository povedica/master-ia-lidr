"""PII redactor tests (feature-065)."""

from __future__ import annotations

from app.embedding_pipeline.pii.redactor import RegexPiiAnalyzer, redact_transcript


def test_redact_transcript_masks_email_when_enabled() -> None:
    analyzer = RegexPiiAnalyzer()
    result = redact_transcript(
        "Reach me at user@example.com today.",
        enabled=True,
        analyzer=analyzer,
    )
    assert "user@example.com" not in result.text
    assert result.entities_redacted >= 1


def test_redact_transcript_noop_when_disabled() -> None:
    text = "Reach me at user@example.com today."
    result = redact_transcript(text, enabled=False, analyzer=RegexPiiAnalyzer())
    assert result.text == text
