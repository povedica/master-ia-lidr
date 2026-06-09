"""Structural JSON chunker for budget components."""

from __future__ import annotations

import logging

import tiktoken

from app.embedding_pipeline.schemas import Budget, BudgetComponent, Chunk

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

    def __init__(self, *, embedding_model: str = _DEFAULT_EMBEDDING_MODEL) -> None:
        self._encoder = _resolve_tiktoken_encoder(embedding_model)

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for budget in budgets:
            for component in budget.components:
                text = self._build_text(budget, component)
                chunks.append(
                    Chunk(
                        chunk_id=f"{budget.budget_id}::{component.component_id}",
                        text=text,
                        metadata=self._build_metadata(budget, component),
                        token_count=len(self._encoder.encode(text)),
                    )
                )
        logger.info(
            "chunker_completed",
            extra={
                "total_budgets": len(budgets),
                "total_chunks": len(chunks),
            },
        )
        return chunks

    def _build_text(self, budget: Budget, component: BudgetComponent) -> str:
        header = (
            f"[Project: {budget.project_summary}] "
            f"[Client sector: {budget.client_metadata.sector} | "
            f"Year: {budget.year} | Main tech: {budget.main_technology}]"
        )
        tech_stack = ", ".join(component.tech_stack)
        return (
            f"{header}\n"
            f"Component: {component.name}\n"
            f"Description: {component.description}\n"
            f"Tech stack: {tech_stack}\n"
            f"Complexity: {component.complexity}\n"
            f"Estimated hours: {component.estimated_hours}"
        )

    def _build_metadata(
        self, budget: Budget, component: BudgetComponent
    ) -> dict[str, object]:
        return {
            "budget_id": budget.budget_id,
            "component_id": component.component_id,
            "client_sector": budget.client_metadata.sector,
            "main_technology": budget.main_technology,
            "year": budget.year,
            "complexity": component.complexity,
            "estimated_hours": component.estimated_hours,
        }
