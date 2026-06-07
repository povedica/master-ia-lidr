"""Unit tests for judge failure artifact writer."""

from __future__ import annotations

from tests.evals.artifacts import write_judge_failure_artifact


def test_write_judge_failure_artifact_creates_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tests.evals.artifacts._ARTIFACTS_DIR", tmp_path)
    path = write_judge_failure_artifact(
        case_id="small-single-turn-web",
        scores={"SessionContextUse": 0.4},
        context_block="## context",
    )
    assert path.exists()
    assert "small-single-turn-web" in path.name
    assert "api_key" not in path.read_text(encoding="utf-8").lower()
