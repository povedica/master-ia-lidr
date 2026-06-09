"""Unit tests for JSONStructuralChunker (feature-031)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import tiktoken

from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.schemas import Budget, BudgetComponent
from tests.embedding_pipeline.conftest import SAMPLE_BUDGET, SAMPLE_BUDGET_COMPONENT

EXPECTED_TEXT = (
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

SECOND_BUDGET = {
    "budget_id": "BUD-2024-099",
    "client_metadata": {"name": "RetailCo", "sector": "retail", "country": "ES"},
    "project_summary": "E-commerce checkout refactor",
    "main_technology": "python",
    "year": 2023,
    "total_estimated_hours": 200,
    "components": [
        {
            "component_id": "PAY-001",
            "name": "Payment gateway integration",
            "description": "Stripe webhook handling",
            "tech_stack": ["python", "fastapi"],
            "estimated_hours": 80,
            "complexity": "medium",
            "dependencies": [],
        },
        {
            "component_id": "PAY-002",
            "name": "Refund workflow",
            "description": "Automated partial refunds",
            "tech_stack": ["python"],
            "estimated_hours": 40,
            "complexity": "low",
            "dependencies": ["PAY-001"],
        },
    ],
}


@pytest.fixture
def encoder() -> tiktoken.Encoding:
    return tiktoken.encoding_for_model("text-embedding-3-small")


@pytest.fixture
def chunker() -> JSONStructuralChunker:
    return JSONStructuralChunker(embedding_model="text-embedding-3-small")


def test_chunk_returns_one_chunk_per_component(chunker: JSONStructuralChunker) -> None:
    budgets = [
        Budget.model_validate(SAMPLE_BUDGET),
        Budget.model_validate(SECOND_BUDGET),
    ]
    chunks = chunker.chunk(budgets)
    assert len(chunks) == 3


def test_chunk_id_format(chunker: JSONStructuralChunker) -> None:
    budget = Budget.model_validate(SAMPLE_BUDGET)
    chunks = chunker.chunk([budget])
    assert chunks[0].chunk_id == "BUD-2024-014::AUTH-001"


def test_chunk_text_matches_template(chunker: JSONStructuralChunker) -> None:
    budget = Budget.model_validate(SAMPLE_BUDGET)
    chunks = chunker.chunk([budget])
    assert chunks[0].text == EXPECTED_TEXT


def test_chunk_metadata_keys_and_values(chunker: JSONStructuralChunker) -> None:
    budget = Budget.model_validate(SAMPLE_BUDGET)
    chunks = chunker.chunk([budget])
    metadata = chunks[0].metadata
    assert set(metadata) == {
        "budget_id",
        "component_id",
        "client_sector",
        "main_technology",
        "year",
        "complexity",
        "estimated_hours",
        "source_name",
        "source_version",
        "location",
    }
    assert metadata == {
        "budget_id": "BUD-2024-014",
        "component_id": "AUTH-001",
        "client_sector": "finance",
        "main_technology": "ruby_on_rails",
        "year": 2024,
        "complexity": "high",
        "estimated_hours": 120,
        "source_name": "inline",
        "source_version": "api",
        "location": "",
    }


def test_token_count_matches_tiktoken_encoding(
    chunker: JSONStructuralChunker, encoder: tiktoken.Encoding
) -> None:
    budget = Budget.model_validate(SAMPLE_BUDGET)
    chunks = chunker.chunk([budget])
    assert chunks[0].token_count > 0
    assert chunks[0].token_count == len(encoder.encode(chunks[0].text))


def test_encoder_instantiated_once_per_chunker() -> None:
    mock_encoder = MagicMock()
    mock_encoder.encode.return_value = [1, 2, 3]
    with patch(
        "app.embedding_pipeline.chunker.tiktoken.encoding_for_model",
        return_value=mock_encoder,
    ) as mock_encoding_for_model:
        chunker = JSONStructuralChunker(embedding_model="text-embedding-3-small")
        budgets = [
            Budget.model_validate(SAMPLE_BUDGET),
            Budget.model_validate(SECOND_BUDGET),
        ]
        chunker.chunk(budgets)
    mock_encoding_for_model.assert_called_once_with("text-embedding-3-small")


def test_chunker_uses_configured_embedding_model() -> None:
    mock_encoder = MagicMock()
    mock_encoder.encode.return_value = [1, 2, 3]
    with patch(
        "app.embedding_pipeline.chunker.tiktoken.encoding_for_model",
        return_value=mock_encoder,
    ) as mock_encoding_for_model:
        chunker = JSONStructuralChunker(embedding_model="text-embedding-3-large")
        chunker.chunk([Budget.model_validate(SAMPLE_BUDGET)])
    mock_encoding_for_model.assert_called_once_with("text-embedding-3-large")


def test_chunker_falls_back_when_model_unknown_to_tiktoken(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fallback_encoder = MagicMock()
    fallback_encoder.encode.return_value = [1, 2, 3]
    with (
        patch(
            "app.embedding_pipeline.chunker.tiktoken.encoding_for_model",
            side_effect=KeyError("unknown"),
        ),
        patch(
            "app.embedding_pipeline.chunker.tiktoken.get_encoding",
            return_value=fallback_encoder,
        ) as mock_get_encoding,
        caplog.at_level("WARNING"),
    ):
        chunker = JSONStructuralChunker(embedding_model="unknown-custom-model")
        chunker.chunk([Budget.model_validate(SAMPLE_BUDGET)])

    mock_get_encoding.assert_called_once_with("cl100k_base")
    assert any(r.message == "chunker_tiktoken_model_fallback" for r in caplog.records)


def test_empty_budgets_returns_empty_list(chunker: JSONStructuralChunker) -> None:
    assert chunker.chunk([]) == []


def test_budget_with_no_components_yields_no_chunks(chunker: JSONStructuralChunker) -> None:
    empty_budget = Budget.model_validate({**SAMPLE_BUDGET, "components": []})
    assert chunker.chunk([empty_budget]) == []


def test_chunk_logs_completion_counts(
    chunker: JSONStructuralChunker, caplog: pytest.LogCaptureFixture
) -> None:
    budgets = [
        Budget.model_validate(SAMPLE_BUDGET),
        Budget.model_validate(SECOND_BUDGET),
    ]
    with caplog.at_level("INFO"):
        chunker.chunk(budgets)
    completion_logs = [r for r in caplog.records if r.message == "chunker_completed"]
    assert len(completion_logs) == 1
    record = completion_logs[0]
    assert record.total_budgets == 2
    assert record.total_chunks == 3


def test_chunk_logs_zero_counts_for_empty_input(
    chunker: JSONStructuralChunker, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO"):
        chunker.chunk([])
    completion_logs = [r for r in caplog.records if r.message == "chunker_completed"]
    assert len(completion_logs) == 1
    record = completion_logs[0]
    assert record.total_budgets == 0
    assert record.total_chunks == 0


def test_chunker_imports_without_api_keys() -> None:
    from app.embedding_pipeline.chunker import JSONStructuralChunker as ImportedChunker

    assert ImportedChunker is JSONStructuralChunker
