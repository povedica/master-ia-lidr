"""Domain errors for the embedding pipeline persistence layer."""

from __future__ import annotations


class DuplicateDocumentError(Exception):
    """Raised when ``source_path`` already exists in ``documents``."""

    def __init__(self, document_id: int, source_path: str) -> None:
        self.document_id = document_id
        self.source_path = source_path
        super().__init__(f"Document already ingested: {source_path}")
