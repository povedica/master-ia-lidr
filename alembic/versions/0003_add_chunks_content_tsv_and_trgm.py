"""Add indexed lexical search columns and indexes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-21
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        ALTER TABLE chunks
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX ix_chunks_content_tsv_gin
        ON chunks
        USING gin (content_tsv)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_chunks_content_trgm
        ON chunks
        USING gin (content gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_trgm")
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv_gin")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
