"""Tests for external prompt text loading."""

from app.context.prompt_loader import load_mode_prompt
from app.services.estimation_engine import EstimationMode


def test_load_mode_prompt_reads_standard_fragment() -> None:
    text = load_mode_prompt(EstimationMode.STANDARD)
    assert "practical estimation" in text.lower()


_MODE_MARKERS: dict[EstimationMode, str] = {
    EstimationMode.BASIC: "basic mode",
    EstimationMode.STANDARD: "standard mode",
    EstimationMode.PROFESSIONAL: "professional mode",
    EstimationMode.EXPERT_REVIEW: "expert review",
}


def test_each_mode_has_prompt_file() -> None:
    for mode in EstimationMode:
        body = load_mode_prompt(mode)
        assert len(body) >= 40
        assert _MODE_MARKERS[mode] in body.lower()


def test_mode_prompts_are_not_identical() -> None:
    basic = load_mode_prompt(EstimationMode.BASIC)
    standard = load_mode_prompt(EstimationMode.STANDARD)
    assert basic != standard
    assert "basic mode" in basic.lower()
    assert "standard mode" in standard.lower()
