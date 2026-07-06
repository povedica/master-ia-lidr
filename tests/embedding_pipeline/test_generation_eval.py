"""Tests for generation eval helpers (FR-14/15/17)."""

from __future__ import annotations

import json
import math

from app.embedding_pipeline.generation_eval import (
    QueryGenerationMetrics,
    RagasSample,
    build_ragas_records,
    format_ragas_answer,
    metrics_to_json,
    render_generation_comparison_markdown,
    render_quality_note,
    summarize_generation_metrics,
)
from app.schemas.rag_estimation_result import RagEstimationLineItem, RagEstimationResult, SourceReference


def test_build_ragas_records_shapes_dataset() -> None:
    records = build_ragas_records(
        [
            RagasSample(
                query_id="q1",
                question="OAuth platform",
                answer='{"summary":"test"}',
                contexts=["chunk text"],
                ground_truth="reference answer",
            )
        ]
    )

    assert records == [
        {
            "question": "OAuth platform",
            "answer": '{"summary":"test"}',
            "contexts": ["chunk text"],
            "ground_truth": "reference answer",
        }
    ]


def test_summarize_generation_metrics_computes_means() -> None:
    per_query = (
        QueryGenerationMetrics("q1", 0.8, 0.7, 0.6, 0.5),
        QueryGenerationMetrics("q2", 0.6, 0.5, 0.4, 0.3),
    )

    metrics = summarize_generation_metrics(per_query)

    assert metrics.mean_faithfulness == 0.7
    assert metrics.mean_context_recall == 0.4


def test_render_generation_comparison_markdown_includes_mean_row() -> None:
    metrics = summarize_generation_metrics(
        (
            QueryGenerationMetrics("q1-oauth-stripe", 0.8, 0.7, 0.6, 0.5),
            QueryGenerationMetrics("q2-jwt-api", 0.6, 0.5, 0.4, 0.3),
        )
    )

    markdown = render_generation_comparison_markdown(metrics)

    assert "q1-oauth-stripe" in markdown
    assert "**mean**" in markdown
    assert "0.700" in markdown


def test_render_quality_note_mentions_weakest_metric() -> None:
    metrics = summarize_generation_metrics(
        (
            QueryGenerationMetrics("q1-oauth-stripe", 0.9, 0.8, 0.7, 0.2),
            QueryGenerationMetrics("q2-jwt-api", 0.8, 0.7, 0.6, 0.3),
        )
    )

    note = render_quality_note(metrics)

    assert "context_recall" in note
    assert "q1-oauth-stripe" in note


def test_format_ragas_answer_uses_prose_not_json() -> None:
    result = RagEstimationResult(
        summary="E-commerce platform with OAuth and Stripe integration.",
        line_items=[
            RagEstimationLineItem(
                component="authentication",
                hours=40.0,
                rationale="OAuth2 login flow from retrieved budget.",
                grounded=True,
                sources=[
                    SourceReference(
                        chunk_id=1,
                        document_id=2,
                        budget_id="BUD-001",
                        evidence="OAuth2 integration",
                    )
                ],
            )
        ],
        total_hours=40.0,
    )

    answer = format_ragas_answer(result)

    assert "authentication" in answer
    assert "40h" in answer
    assert "{" not in answer


def test_metrics_to_json_replaces_nan_with_null() -> None:
    metrics = summarize_generation_metrics(
        (
            QueryGenerationMetrics("q1", 0.5, math.nan, 0.8, 0.1),
            QueryGenerationMetrics("q2", 0.6, math.nan, 0.9, 0.2),
        )
    )

    payload = metrics_to_json(metrics)
    serialized = json.dumps(payload)

    assert "NaN" not in serialized
    assert payload["per_query"][0]["answer_relevancy"] is None
    assert payload["mean"]["answer_relevancy"] is None


def test_render_generation_comparison_markdown_shows_na_for_nan_metrics() -> None:
    metrics = summarize_generation_metrics(
        (
            QueryGenerationMetrics("q1-oauth-stripe", 0.5, math.nan, 0.8, 0.0),
            QueryGenerationMetrics("q2-jwt-api", 0.6, math.nan, 0.9, 0.0),
        )
    )

    markdown = render_generation_comparison_markdown(metrics)

    assert "n/a" in markdown
    assert "nan" not in markdown.lower()


def test_render_quality_note_mentions_broken_metric_columns() -> None:
    metrics = summarize_generation_metrics(
        (
            QueryGenerationMetrics("q1-oauth-stripe", 0.5, math.nan, 0.8, 0.0),
            QueryGenerationMetrics("q2-jwt-api", 0.6, math.nan, 0.9, 0.0),
        )
    )

    note = render_quality_note(metrics)

    assert "answer_relevancy" in note
