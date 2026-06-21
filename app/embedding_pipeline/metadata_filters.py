"""Shared SQLAlchemy predicates for retrieval debug metadata filters."""

from __future__ import annotations

from sqlalchemy import Integer, cast
from sqlalchemy.sql.elements import ColumnElement

from app.embedding_pipeline.retrieval_debug_schemas import RetrievalMetadataFilters
from app.models.chunk import Chunk as ChunkModel
from app.models.document import Document as DocumentModel

_SCALAR_METADATA_KEYS = (
    "client_sector",
    "main_technology",
    "source_name",
    "language",
)


def build_metadata_filters(
    filters: RetrievalMetadataFilters | None,
) -> list[ColumnElement[bool]]:
    """Build AND-combinable SQL predicates for retrieval debug metadata filters."""

    if filters is None:
        return []

    predicates: list[ColumnElement[bool]] = []
    for key in _SCALAR_METADATA_KEYS:
        value = getattr(filters, key)
        if value is not None:
            predicates.append(ChunkModel.metadata_.contains({key: value}))

    if filters.tags:
        predicates.append(ChunkModel.metadata_["tags"].contains(filters.tags))

    if filters.year is not None:
        year_value = cast(ChunkModel.metadata_["year"].astext, Integer)
        if filters.year.from_ is not None:
            predicates.append(year_value >= filters.year.from_)
        if filters.year.to is not None:
            predicates.append(year_value <= filters.year.to)

    if filters.document_type is not None:
        predicates.append(DocumentModel.document_type == filters.document_type)

    return predicates
