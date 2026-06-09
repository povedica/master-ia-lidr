"""Tests for ingest_from_dir CLI (feature-035)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk
from app.scripts import ingest_from_dir

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "budget_files"
EMBEDDING_DIM = 1536


def test_ingest_from_dir_dry_run_prints_chunk_summary(capsys) -> None:
    exit_code = ingest_from_dir.main(
        ["--dir", str(FIXTURES_DIR), "--dry-run"],
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "chunks=3" in captured.out
    assert "BUD-2024-014::AUTH-001" in captured.out


def test_ingest_from_dir_full_path_prints_stats(capsys) -> None:
    mock_embedded = [
        EmbeddedChunk(
            chunk_id="id",
            text="t",
            metadata={},
            token_count=1,
            embedding=[0.1] * EMBEDDING_DIM,
        )
    ]
    with (
        patch("app.scripts.ingest_from_dir.get_settings") as mock_settings,
        patch("app.scripts.ingest_from_dir.OpenAIEmbedder") as mock_embedder_cls,
        patch(
            "app.scripts.ingest_from_dir.run_ingest",
            new_callable=AsyncMock,
        ) as mock_run,
    ):
        mock_settings.return_value = MagicMock()
        mock_embedder_cls.return_value = MagicMock()
        mock_run.return_value = MagicMock(
            stats=MagicMock(
                total_budgets=3,
                total_chunks=3,
                total_tokens=100,
                estimated_cost_usd=0.000002,
            )
        )
        exit_code = ingest_from_dir.main(["--dir", str(FIXTURES_DIR)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "total_budgets=3" in captured.out
    assert "total_chunks=3" in captured.out
    mock_run.assert_awaited_once()
