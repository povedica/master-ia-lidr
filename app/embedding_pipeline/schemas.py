"""Pydantic data models for the embedding pipeline ingest contract."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClientMetadata(BaseModel):
    name: str
    sector: str
    country: str


class BudgetComponent(BaseModel):
    component_id: str
    name: str
    description: str
    tech_stack: list[str]
    estimated_hours: int
    complexity: str
    dependencies: list[str]


class Budget(BaseModel):
    budget_id: str
    client_metadata: ClientMetadata
    project_summary: str
    main_technology: str
    year: int
    total_estimated_hours: int
    components: list[BudgetComponent]


class PipelineDocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    source_version: str
    ingested_at: str
    lineage: list[str] = Field(default_factory=list)
    location: str = ""
    extra: dict[str, object] = Field(default_factory=dict)
    sensitivity_access_level: str = "internal"


class PipelineDocument(BaseModel):
    id: str
    text: str
    metadata: PipelineDocumentMetadata


class Chunk(BaseModel):
    chunk_id: str
    text: str
    metadata: dict[str, object]
    token_count: int


class EmbeddedChunk(Chunk):
    embedding: list[float]


class IngestStats(BaseModel):
    total_budgets: int
    total_chunks: int
    total_tokens: int
    estimated_cost_usd: float


class IngestRequest(BaseModel):
    budgets: list[Budget]


class IngestResponse(BaseModel):
    chunks: list[EmbeddedChunk]
    stats: IngestStats


class PersistentIngestRequest(BaseModel):
    """HTTP ingest contract: one budget document persisted by ``source_path``."""

    source_path: str
    document_type: str
    content: Budget
    metadata: dict[str, object] = Field(default_factory=dict)


class PersistentIngestResponse(BaseModel):
    """Metadata returned after a successful persisted ingest."""

    document_id: int
    chunks_created: int
    embedding_dimension: int
    ingestion_time_ms: int
