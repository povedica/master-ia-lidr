"""Tests for external prompt text loading."""

from app.prompts.loader import load_mode_prompt
from app.services.estimation_engine import EstimationMode


def test_load_mode_prompt_reads_standard_fragment() -> None:
    text = load_mode_prompt(EstimationMode.STANDARD)
    assert "practical estimate" in text.lower()


def test_each_mode_has_prompt_file() -> None:
    for mode in EstimationMode:
        body = load_mode_prompt(mode)
        assert len(body) >= 40
