"""Unit tests for embedding pipeline loaders (feature-035)."""

from __future__ import annotations

from pathlib import Path

from app.embedding_pipeline.loaders.filesystem import FileSystemLoader

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "budget_files"


def test_filesystem_loader_yields_only_json_in_directory(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "c.json").write_text("{}", encoding="utf-8")

    paths = list(FileSystemLoader.iter_budget_files(tmp_path))

    assert paths == [tmp_path / "a.json"]


def test_filesystem_loader_reads_fixture_directory() -> None:
    paths = list(FileSystemLoader.iter_budget_files(FIXTURES_DIR))
    assert len(paths) == 13
    assert all(path.suffix == ".json" for path in paths)
