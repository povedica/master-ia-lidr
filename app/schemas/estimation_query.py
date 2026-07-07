"""Structured query facets for RAG retrieval reformulation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class EstimationQuery(BaseModel):
    """Search-oriented facets extracted from a question or transcript."""

    question: str = Field(..., min_length=1)
    search_facets: list[str] = Field(default_factory=list)
    component_hints: list[str] = Field(default_factory=list)
    sector_filters: list[str] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped


def compose_search_text(query: EstimationQuery) -> str:
    """Build a deterministic retrieval query string from reformulated facets."""

    parts: list[str] = [query.question]

    if query.search_facets:
        parts.append(f"facets: {', '.join(query.search_facets)}")
    if query.component_hints:
        parts.append(f"components: {', '.join(query.component_hints)}")
    if query.sector_filters:
        parts.append(f"sectors: {', '.join(query.sector_filters)}")

    return " | ".join(parts)
