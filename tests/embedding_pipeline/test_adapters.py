"""Unit tests for BudgetToDocumentAdapter (feature-035)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.embedding_pipeline.adapters import (
    BudgetToDocumentAdapter,
    build_component_markdown,
    make_component_id,
)
from app.embedding_pipeline.schemas import Budget, PipelineDocumentMetadata
from tests.embedding_pipeline.conftest import SAMPLE_BUDGET
from tests.embedding_pipeline.test_chunker import SECOND_BUDGET

EXPECTED_MARKDOWN = (
    "## Project context\n"
    "- Summary: Mobile banking API with OAuth 2.0 authentication\n"
    "- Sector: finance | Year: 2024 | Main tech: ruby_on_rails\n"
    "\n"
    "## Component: OAuth 2.0 authentication backend\n"
    "Implementation of OAuth 2.0 flows with JWT session management\n"
    "\n"
    "### Tech stack\n"
    "ruby_on_rails, postgresql, redis\n"
    "\n"
    "### Estimate\n"
    "- Complexity: high\n"
    "- Hours: 120"
)


def test_make_component_id_uses_double_colon() -> None:
    assert make_component_id("BUD-2024-014", "AUTH-001") == "BUD-2024-014::AUTH-001"


def test_build_component_markdown_matches_template() -> None:
    budget = Budget.model_validate(SAMPLE_BUDGET)
    text = build_component_markdown(budget, budget.components[0])
    assert text == EXPECTED_MARKDOWN


def test_adapter_produces_one_document_per_component() -> None:
    adapter = BudgetToDocumentAdapter()
    budget = Budget.model_validate(SECOND_BUDGET)
    documents = adapter.budget_to_documents(budget)
    assert len(documents) == 2


def test_adapter_document_id_matches_chunk_id_format() -> None:
    adapter = BudgetToDocumentAdapter()
    budget = Budget.model_validate(SAMPLE_BUDGET)
    documents = adapter.budget_to_documents(budget)
    assert documents[0].id == "BUD-2024-014::AUTH-001"


def test_adapter_inline_defaults_for_http_ingest() -> None:
    adapter = BudgetToDocumentAdapter()
    budget = Budget.model_validate(SAMPLE_BUDGET)
    metadata = adapter.budget_to_documents(budget)[0].metadata
    assert metadata.source_name == "inline"
    assert metadata.source_version == "api"
    assert metadata.location == ""
    assert metadata.sensitivity_access_level == "internal"


def test_adapter_metadata_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PipelineDocumentMetadata.model_validate(
            {
                "source_name": "inline",
                "source_version": "api",
                "ingested_at": "2026-06-09T00:00:00Z",
                "lineage": [],
                "location": "",
                "extra": {},
                "unexpected": "nope",
            }
        )
