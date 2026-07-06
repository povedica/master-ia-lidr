"""Read chunk content by id for RAG context assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk as ChunkModel


def _budget_id(metadata: dict[str, Any]) -> str | None:
    raw = metadata.get("budget_id")
    return str(raw) if raw is not None else None


@dataclass(frozen=True)
class ChunkContent:
    chunk_id: int
    document_id: int
    budget_id: str | None
    content: str
    metadata: dict[str, Any]


class ChunkContentRepository:
    """Read-only access to persisted chunk text for generation."""

    def build_contents_by_ids_statement(
        self,
        chunk_ids: Sequence[int],
    ) -> Select[tuple[ChunkModel]]:
        return select(ChunkModel).where(ChunkModel.id.in_(chunk_ids))

    async def get_contents_by_ids(
        self,
        session: AsyncSession,
        chunk_ids: Sequence[int],
    ) -> dict[int, ChunkContent]:
        """Return content keyed by chunk_id; missing ids are simply absent."""

        if not chunk_ids:
            return {}

        result = await session.execute(self.build_contents_by_ids_statement(chunk_ids))
        rows = result.scalars().all()
        return {
            chunk.id: ChunkContent(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                budget_id=_budget_id(dict(chunk.metadata_)),
                content=chunk.content,
                metadata=dict(chunk.metadata_),
            )
            for chunk in rows
        }
