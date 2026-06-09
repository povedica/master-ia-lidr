"""SQLAlchemy ORM metadata tests for semantic search persistence."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base
from app.models.chunk import Chunk
from app.models.document import Document


def test_documents_table_metadata() -> None:
    table = Document.__table__
    assert table.name == "documents"
    assert table.c.id.type.__class__ is BigInteger
    assert isinstance(table.c.source_path.type, Text)
    assert table.c.document_type.nullable is False
    assert table.c.ingested_at.nullable is False
    assert isinstance(table.c.metadata.type, JSONB)
    assert any(index.name == "ix_documents_source_path" for index in table.indexes)
    unique = {constraint.name for constraint in table.constraints if isinstance(constraint, UniqueConstraint)}
    assert "uq_documents_source_path" in unique


def test_chunks_table_metadata() -> None:
    table = Chunk.__table__
    assert table.name == "chunks"
    assert table.c.id.type.__class__ is BigInteger
    fk = next(
        constraint
        for constraint in table.foreign_key_constraints
        if "document_id" in {col.name for col in constraint.columns}
    )
    assert fk.ondelete == "CASCADE"
    assert table.c.chunk_type.nullable is False
    assert isinstance(table.c.content.type, Text)
    assert table.c.embedding.type.dim == 1536  # type: ignore[attr-defined]
    assert isinstance(table.c.metadata.type, JSONB)
    index_names = {index.name for index in table.indexes}
    assert "ix_chunks_document_id" in index_names
    assert "ix_chunks_chunk_type" in index_names
    assert "ix_chunks_metadata_gin" in index_names


def test_base_metadata_registers_both_tables() -> None:
    table_names = set(Base.metadata.tables)
    assert table_names == {"documents", "chunks"}


def test_chunks_document_id_foreign_key_targets_documents() -> None:
    table = Chunk.__table__
    document_id_col = table.c.document_id
    assert isinstance(document_id_col.type, BigInteger)
    fk = next(iter(document_id_col.foreign_keys))
    assert fk.target_fullname == "documents.id"
    assert fk.ondelete == "CASCADE"
