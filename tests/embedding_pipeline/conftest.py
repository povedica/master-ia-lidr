"""Pydantic schemas for the embedding pipeline (Session 07, increment 1)."""

from __future__ import annotations

SAMPLE_CLIENT_METADATA = {
    "name": "FintechCorp",
    "sector": "finance",
    "country": "ES",
}

SAMPLE_BUDGET_COMPONENT = {
    "component_id": "AUTH-001",
    "name": "OAuth 2.0 authentication backend",
    "description": "Implementation of OAuth 2.0 flows with JWT session management",
    "tech_stack": ["ruby_on_rails", "postgresql", "redis"],
    "estimated_hours": 120,
    "complexity": "high",
    "dependencies": [],
}

SAMPLE_BUDGET = {
    "budget_id": "BUD-2024-014",
    "client_metadata": SAMPLE_CLIENT_METADATA,
    "project_summary": "Mobile banking API with OAuth 2.0 authentication",
    "main_technology": "ruby_on_rails",
    "year": 2024,
    "total_estimated_hours": 480,
    "components": [SAMPLE_BUDGET_COMPONENT],
}

SAMPLE_CHUNK = {
    "chunk_id": "BUD-2024-014:AUTH-001",
    "text": "OAuth 2.0 authentication backend for FintechCorp",
    "metadata": {"budget_id": "BUD-2024-014", "component_id": "AUTH-001"},
    "token_count": 42,
}

SAMPLE_EMBEDDING = [0.1, 0.2, 0.3]

SAMPLE_INGEST_STATS = {
    "total_budgets": 1,
    "total_chunks": 1,
    "total_tokens": 42,
    "estimated_cost_usd": 0.0001,
}
