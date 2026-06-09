"""Embedding pipeline Pydantic schema contract tests."""

import pytest
from pydantic import ValidationError

from app.embedding_pipeline.schemas import (
    Budget,
    BudgetComponent,
    Chunk,
    ClientMetadata,
    EmbeddedChunk,
    IngestRequest,
    IngestResponse,
    IngestStats,
)
from tests.embedding_pipeline.conftest import (
    SAMPLE_BUDGET,
    SAMPLE_BUDGET_COMPONENT,
    SAMPLE_CHUNK,
    SAMPLE_CLIENT_METADATA,
    SAMPLE_EMBEDDING,
    SAMPLE_INGEST_STATS,
)


def test_client_metadata_from_valid_data() -> None:
    metadata = ClientMetadata.model_validate(SAMPLE_CLIENT_METADATA)
    assert metadata.name == "FintechCorp"
    assert metadata.sector == "finance"
    assert metadata.country == "ES"


def test_budget_component_from_valid_data() -> None:
    component = BudgetComponent.model_validate(SAMPLE_BUDGET_COMPONENT)
    assert component.component_id == "AUTH-001"
    assert component.complexity == "high"
    assert component.tech_stack == ["ruby_on_rails", "postgresql", "redis"]


def test_budget_from_valid_data() -> None:
    budget = Budget.model_validate(SAMPLE_BUDGET)
    assert budget.budget_id == "BUD-2024-014"
    assert budget.client_metadata.name == "FintechCorp"
    assert len(budget.components) == 1
    assert budget.components[0].component_id == "AUTH-001"


def test_chunk_from_valid_data() -> None:
    chunk = Chunk.model_validate(SAMPLE_CHUNK)
    assert chunk.chunk_id == "BUD-2024-014::AUTH-001"
    assert chunk.token_count == 42


def test_embedded_chunk_is_subclass_of_chunk() -> None:
    assert issubclass(EmbeddedChunk, Chunk)


def test_embedded_chunk_from_valid_data() -> None:
    embedded = EmbeddedChunk.model_validate({**SAMPLE_CHUNK, "embedding": SAMPLE_EMBEDDING})
    assert embedded.embedding == SAMPLE_EMBEDDING
    assert embedded.chunk_id == SAMPLE_CHUNK["chunk_id"]


def test_embedded_chunk_rejects_missing_embedding() -> None:
    with pytest.raises(ValidationError):
        EmbeddedChunk.model_validate(SAMPLE_CHUNK)


def test_ingest_stats_from_valid_data() -> None:
    stats = IngestStats.model_validate(SAMPLE_INGEST_STATS)
    assert stats.total_budgets == 1
    assert stats.estimated_cost_usd == pytest.approx(0.0001)


def test_ingest_request_from_valid_data() -> None:
    request = IngestRequest.model_validate({"budgets": [SAMPLE_BUDGET]})
    assert len(request.budgets) == 1
    assert request.budgets[0].budget_id == "BUD-2024-014"


def test_ingest_response_stats_serialize_required_keys() -> None:
    response = IngestResponse(
        chunks=[
            EmbeddedChunk.model_validate({**SAMPLE_CHUNK, "embedding": SAMPLE_EMBEDDING})
        ],
        stats=IngestStats.model_validate(SAMPLE_INGEST_STATS),
    )
    stats = response.model_dump()["stats"]
    assert set(stats) == {
        "total_budgets",
        "total_chunks",
        "total_tokens",
        "estimated_cost_usd",
    }


def test_public_schema_imports() -> None:
    from app.embedding_pipeline.schemas import (  # noqa: PLC0415
        Budget as ImportedBudget,
        Chunk as ImportedChunk,
        EmbeddedChunk as ImportedEmbeddedChunk,
        IngestRequest as ImportedIngestRequest,
        IngestResponse as ImportedIngestResponse,
    )

    assert ImportedBudget is Budget
    assert ImportedChunk is Chunk
    assert ImportedEmbeddedChunk is EmbeddedChunk
    assert ImportedIngestRequest is IngestRequest
    assert ImportedIngestResponse is IngestResponse
