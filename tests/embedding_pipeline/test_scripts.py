"""Tests for embedding pipeline CLI scripts (feature-035)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.scripts import architecture_decision, inspect_fixtures, preflight_embedding_pipeline

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "budget_files"


def test_preflight_missing_key_exits_one(capsys) -> None:
    with patch(
        "app.scripts.preflight_embedding_pipeline.get_settings",
    ) as mock_settings:
        mock_settings.return_value.openai_api_key = ""
        mock_settings.return_value.embedding_pipeline_model = "text-embedding-3-small"
        exit_code = preflight_embedding_pipeline.main([])

    assert exit_code == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_preflight_skip_key_check_exits_zero(capsys) -> None:
    with patch(
        "app.scripts.preflight_embedding_pipeline.get_settings",
    ) as mock_settings:
        mock_settings.return_value.openai_api_key = ""
        mock_settings.return_value.embedding_pipeline_model = "text-embedding-3-small"
        exit_code = preflight_embedding_pipeline.main(["--skip-key-check"])

    assert exit_code == 0
    assert "settings=ok" in capsys.readouterr().out


def test_architecture_decision_outputs_recommendation(capsys) -> None:
    exit_code = architecture_decision.main(["--corpus-tokens", "5000", "--refresh-days", "60"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "CAG"


def test_inspect_fixtures_reports_counts(capsys) -> None:
    exit_code = inspect_fixtures.main(["--dir", str(FIXTURES_DIR)])
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "files=3 valid=3 invalid=0 total_components=3" in captured
