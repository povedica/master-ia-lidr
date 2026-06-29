"""Tests for generation eval helpers (FR-14/15)."""

from __future__ import annotations

from app.embedding_pipeline.generation_eval import (
    QueryGenerationMetrics,
    RagasSample,
    build_ragas_records,
    render_generation_comparison_markdown,
    render_quality_note,
    summarize_generation_metrics,
)


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
