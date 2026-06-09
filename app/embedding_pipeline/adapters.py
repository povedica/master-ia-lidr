"""Adapters between upstream budget records and pipeline documents."""

from __future__ import annotations

from datetime import UTC, datetime

from app.embedding_pipeline.schemas import (
    Budget,
    BudgetComponent,
    PipelineDocument,
    PipelineDocumentMetadata,
)


def make_component_id(budget_id: str, component_id: str) -> str:
    return f"{budget_id}::{component_id}"


def build_component_markdown(budget: Budget, component: BudgetComponent) -> str:
    tech_stack = ", ".join(component.tech_stack)
    return (
        "## Project context\n"
        f"- Summary: {budget.project_summary}\n"
        f"- Sector: {budget.client_metadata.sector} | Year: {budget.year} | "
        f"Main tech: {budget.main_technology}\n"
        "\n"
        f"## Component: {component.name}\n"
        f"{component.description}\n"
        "\n"
        "### Tech stack\n"
        f"{tech_stack}\n"
        "\n"
        "### Estimate\n"
        f"- Complexity: {component.complexity}\n"
        f"- Hours: {component.estimated_hours}"
    )


class BudgetToDocumentAdapter:
    """Map one budget into one pipeline document per component."""

    def __init__(
        self,
        *,
        source_name: str = "inline",
        source_version: str = "api",
        location: str = "",
        lineage: list[str] | None = None,
    ) -> None:
        self._source_name = source_name
        self._source_version = source_version
        self._location = location
        self._lineage = list(lineage or [])

    def budget_to_documents(self, budget: Budget) -> list[PipelineDocument]:
        ingested_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )
        documents: list[PipelineDocument] = []
        for component in budget.components:
            documents.append(
                PipelineDocument(
                    id=make_component_id(budget.budget_id, component.component_id),
                    text=build_component_markdown(budget, component),
                    metadata=PipelineDocumentMetadata(
                        source_name=self._source_name,
                        source_version=self._source_version,
                        ingested_at=ingested_at,
                        lineage=self._lineage,
                        location=self._location,
                    ),
                )
            )
        return documents
