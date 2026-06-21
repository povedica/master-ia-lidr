"""Tests for retrieval debug metadata filter SQL predicates."""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from app.embedding_pipeline.metadata_filters import build_metadata_filters
from app.embedding_pipeline.retrieval_debug_schemas import RetrievalMetadataFilters


def _compiled_predicates(filters: RetrievalMetadataFilters) -> tuple[str, list[object]]:
    predicates = build_metadata_filters(filters)
    compiled = [
        predicate.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False})
        for predicate in predicates
    ]
    sql = "\n".join(str(predicate) for predicate in compiled)
    params: list[object] = []
    for predicate in compiled:
        params.extend(predicate.params.values())
    return sql, params


def test_build_metadata_filters_returns_empty_list_without_filters() -> None:
    assert build_metadata_filters(None) == []


def test_build_metadata_filters_uses_jsonb_containment_for_scalar_metadata() -> None:
    sql, params = _compiled_predicates(
        RetrievalMetadataFilters(
            client_sector="finance",
            main_technology="python",
            source_name="budget_2024_q1",
            language="en",
        )
    )

    assert sql.count("@>") == 4
    assert {"client_sector": "finance"} in params
    assert {"main_technology": "python"} in params
    assert {"source_name": "budget_2024_q1"} in params
    assert {"language": "en"} in params


def test_build_metadata_filters_uses_contains_all_semantics_for_tags() -> None:
    sql, params = _compiled_predicates(RetrievalMetadataFilters(tags=["backend", "api"]))

    assert "@>" in sql
    assert ["backend", "api"] in params


def test_build_metadata_filters_uses_inclusive_year_bounds() -> None:
    sql, params = _compiled_predicates(RetrievalMetadataFilters(year={"from": 2023, "to": 2025}))

    assert ">=" in sql
    assert "<=" in sql
    assert "year" in params
    assert 2023 in params
    assert 2025 in params


def test_build_metadata_filters_uses_document_type_column() -> None:
    sql, params = _compiled_predicates(RetrievalMetadataFilters(document_type="historical_budget"))

    assert "documents.document_type" in sql
    assert "historical_budget" in params
