"""Structural JSON chunker for budget components."""

from __future__ import annotations

import logging

import tiktoken

from app.embedding_pipeline.adapters import BudgetToDocumentAdapter
from app.embedding_pipeline.schemas import Budget, BudgetComponent, Chunk, PipelineDocument

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_TIKTOKEN_FALLBACK_ENCODING = "cl100k_base"


def _resolve_tiktoken_encoder(embedding_model: str) -> tiktoken.Encoding:
    model = embedding_model.strip() or _DEFAULT_EMBEDDING_MODEL
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        logger.warning(
            "chunker_tiktoken_model_fallback",
            extra={
                "requested_model": model,
                "fallback_encoding": _TIKTOKEN_FALLBACK_ENCODING,
            },
        )
        return tiktoken.get_encoding(_TIKTOKEN_FALLBACK_ENCODING)


class JSONStructuralChunker:
    """Turn budgets into one chunk per component with parent-budget context."""

    def __init__(
        self,
        *,
        embedding_model: str = _DEFAULT_EMBEDDING_MODEL,
        adapter: BudgetToDocumentAdapter | None = None,
    ) -> None:
        self._encoder = _resolve_tiktoken_encoder(embedding_model)
        self._adapter = adapter or BudgetToDocumentAdapter()

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for budget in budgets:
            documents = self._adapter.budget_to_documents(budget)
            for document, component in zip(
                documents, budget.components, strict=True
            ):
                chunks.append(self._document_to_chunk(document, budget, component))
        logger.info(
            "chunker_completed",
            extra={
                "total_budgets": len(budgets),
                "total_chunks": len(chunks),
            },
        )
        return chunks

    def _document_to_chunk(
        self,
        document: PipelineDocument,
        budget: Budget,
        component: BudgetComponent,
    ) -> Chunk:
        text = document.text
        metadata: dict[str, object] = {
            "budget_id": budget.budget_id,
            "component_id": component.component_id,
            "client_sector": budget.client_metadata.sector,
            "main_technology": budget.main_technology,
            "year": budget.year,
            "complexity": component.complexity,
            "estimated_hours": component.estimated_hours,
            "source_name": document.metadata.source_name,
            "source_version": document.metadata.source_version,
            "location": document.metadata.location,
        }
        if document.metadata.lineage:
            metadata["lineage"] = document.metadata.lineage
        return Chunk(
            chunk_id=document.id,
            text=text,
            metadata=metadata,
            token_count=len(self._encoder.encode(text)),
        )
