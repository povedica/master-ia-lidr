"""Add collection discriminator to chunks for multi-index retrieval.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "collection",
            sa.String(length=64),
            nullable=False,
            server_default="budgets",
        ),
    )
    op.create_index(
        "ix_chunks_collection_chunk_type",
        "chunks",
        ["collection", "chunk_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_collection_chunk_type", table_name="chunks")
    op.drop_column("chunks", "collection")
