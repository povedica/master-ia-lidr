"""Smoke checks for Session 13 exercise assets."""

from __future__ import annotations

from pathlib import Path

SESSION_13_DIR = Path(__file__).resolve().parents[2] / "exercises" / "session-13"
REQUIRED_FILES = (
    "sample_transcript_complex.txt",
    "demo_ciclo_completo.txt",
    "README.md",
)


def test_session_13_assets_exist() -> None:
    for name in REQUIRED_FILES:
        path = SESSION_13_DIR / name
        assert path.is_file(), f"missing {name}"
        assert path.stat().st_size > 0, f"empty {name}"


def test_session_13_readme_documents_cli_flags() -> None:
    readme = (SESSION_13_DIR / "README.md").read_text(encoding="utf-8")
    assert "run_graph_s13.py" in readme
    assert "--memory" in readme
    assert "--stub" in readme
    assert "app/services/estimation_graph" in readme


def test_complex_transcript_mentions_multiple_components() -> None:
    text = (SESSION_13_DIR / "sample_transcript_complex.txt").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "ruta" in lowered or "plataforma" in lowered
    assert "backend" in lowered or "api" in lowered
    assert "móvil" in lowered or "mobile" in lowered or "app" in lowered
