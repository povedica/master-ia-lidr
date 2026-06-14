"""Static checks for Alembic migrations."""

from __future__ import annotations

from pathlib import Path


def _migration_source(filename: str) -> str:
    return (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / filename
    ).read_text(encoding="utf-8")


def test_initial_migration_creates_pgvector_extension() -> None:
    source = _migration_source("0001_initial_schema.py")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in source
    assert "Vector(1536)" in source
    assert "ix_chunks_metadata_gin" in source
    assert "ondelete=\"CASCADE\"" in source or "ondelete='CASCADE'" in source


def test_hnsw_migration_creates_cosine_index_on_embedding() -> None:
    source = _migration_source("0002_add_chunks_embedding_hnsw_index.py")
    assert 'down_revision: str | None = "0001"' in source or 'down_revision = "0001"' in source
    assert "ix_chunks_embedding_hnsw" in source
    assert "USING hnsw" in source or "using hnsw" in source.lower()
    assert "vector_cosine_ops" in source
    assert "embedding IS NOT NULL" in source
    assert "m = 16" in source or "m=16" in source
    assert "ef_construction = 64" in source or "ef_construction=64" in source
