"""Response output persistence tests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.services import response_output_writer


def test_build_output_filename_uses_expected_utc_format() -> None:
    value = response_output_writer.build_output_filename(
        datetime(2026, 4, 30, 15, 55, 9, tzinfo=UTC)
    )
    assert value == "response-20260430-155509.md"


def test_persist_estimation_output_creates_markdown_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(response_output_writer, "_OUTPUT_DIR", tmp_path)
    destination = response_output_writer.persist_estimation_output("## Estimation: mocked")

    assert destination.parent == tmp_path
    assert destination.name.startswith("response-")
    assert destination.name.endswith(".md")
    assert destination.read_text(encoding="utf-8") == "## Estimation: mocked"
