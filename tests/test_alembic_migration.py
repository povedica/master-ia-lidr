"""Static checks for the initial Alembic migration."""

from __future__ import annotations

from pathlib import Path


def test_initial_migration_creates_pgvector_extension() -> None:
    migration_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "0001_initial_schema.py"
    )
    source = migration_path.read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in source
    assert "Vector(1536)" in source
    assert "ix_chunks_metadata_gin" in source
    assert "ondelete=\"CASCADE\"" in source or "ondelete='CASCADE'" in source
