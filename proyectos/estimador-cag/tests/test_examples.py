"""Tests for file-based few-shot examples loading."""

from pathlib import Path

from app.context import examples as examples_module
from app.services.estimation_engine import EstimationMode


def _write_example(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_normalize_example_text_preserves_markdown_newlines() -> None:
    raw = "Line one.\n\nLine two.\r\nLine three.\n\n\n\nExtra gap."
    normalized = examples_module._normalize_example_text(raw)
    assert "Line one." in normalized
    assert "Line two." in normalized
    assert "Line three." in normalized
    assert "\n" in normalized


def test_load_examples_returns_random_subset_between_two_and_four(
    tmp_path: Path,
    monkeypatch,
) -> None:
    standard = tmp_path / "standard"
    standard.mkdir(parents=True)
    for index in range(1, 6):
        _write_example(
            standard / f"sample-standard-{index:02d}.txt",
            f"## Title {index}\n\n### Task Breakdown\n\n| Task | Hours | Cost (EUR) |\n|------|------:|------------|\n| A | 1 | 100 |\n\n### Totals\n\n- **Total hours:** 1\n- **Total cost:** 100 EUR\n",
        )

    monkeypatch.setattr(examples_module, "_EXAMPLES_ROOT", tmp_path)
    monkeypatch.setattr(examples_module.random, "randint", lambda _a, _b: 4)

    examples = examples_module.load_examples(EstimationMode.STANDARD)
    assert len(examples) == 4
    assert all("Historical standard estimation sample" in example.meeting_summary for example in examples)
    assert all("\n" in example.estimation for example in examples)


def test_load_examples_returns_all_when_pool_has_two_or_less(
    tmp_path: Path,
    monkeypatch,
) -> None:
    standard = tmp_path / "standard"
    standard.mkdir(parents=True)
    _write_example(standard / "sample-standard-01.txt", "estimate one")
    _write_example(standard / "sample-standard-02.txt", "estimate two")

    monkeypatch.setattr(examples_module, "_EXAMPLES_ROOT", tmp_path)

    examples = examples_module.load_examples(EstimationMode.STANDARD)
    assert len(examples) == 2


def test_load_examples_falls_back_to_standard_when_mode_dir_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    standard = tmp_path / "standard"
    basic = tmp_path / "basic"
    standard.mkdir(parents=True)
    basic.mkdir(parents=True)
    _write_example(standard / "sample-standard-01.txt", "standard body one")
    _write_example(standard / "sample-standard-02.txt", "standard body two")

    monkeypatch.setattr(examples_module, "_EXAMPLES_ROOT", tmp_path)

    examples = examples_module.load_examples(EstimationMode.BASIC)
    assert len(examples) == 2
    assert all(ex.estimation.startswith("standard body") for ex in examples)
