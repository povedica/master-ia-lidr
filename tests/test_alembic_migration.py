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


def test_indexed_lexical_migration_creates_tsvector_and_trigram_indexes() -> None:
    source = _migration_source("0003_add_chunks_content_tsv_and_trgm.py")
    normalized_source = " ".join(source.split())

    assert 'down_revision: str | None = "0002"' in source or 'down_revision = "0002"' in source
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in source
    assert "content_tsv" in source
    assert "GENERATED ALWAYS AS" in source
    assert "to_tsvector('english', content)" in normalized_source
    assert "ix_chunks_content_tsv_gin" in source
    assert "USING gin (content_tsv)" in normalized_source
    assert "ix_chunks_content_trgm" in source
    assert "gin_trgm_ops" in source
    assert "DROP INDEX IF EXISTS ix_chunks_content_trgm" in source
    assert "DROP INDEX IF EXISTS ix_chunks_content_tsv_gin" in source
    assert "DROP COLUMN IF EXISTS content_tsv" in source


def test_spanish_lexical_migration_regenerates_content_tsv_and_round_trips() -> None:
    source = _migration_source("0004_set_chunks_content_tsv_spanish.py")
    normalized_source = " ".join(source.split())

    assert 'down_revision: str | None = "0003"' in source or 'down_revision = "0003"' in source
    assert "to_tsvector('spanish', content)" in normalized_source
    assert "ix_chunks_content_tsv_gin" in source
    assert "USING gin (content_tsv)" in normalized_source
    assert "DROP INDEX IF EXISTS ix_chunks_content_tsv_gin" in source
    assert "DROP COLUMN IF EXISTS content_tsv" in source
    downgrade_section = source.split("def downgrade", maxsplit=1)[1]
    assert "to_tsvector('english', content)" in " ".join(downgrade_section.split())
