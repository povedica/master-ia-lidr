"""Evaluation helpers for grounded generation quality (feature-052)."""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from app.schemas.rag_estimation_result import RagEstimationResult


@dataclass(frozen=True)
class GenerationGoldenQuery:
    id: str
    question: str
    ground_truth: str


@dataclass(frozen=True)
class RagasSample:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    query_id: str = ""


@dataclass(frozen=True)
class QueryGenerationMetrics:
    query_id: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


@dataclass(frozen=True)
class GenerationMetrics:
    per_query: tuple[QueryGenerationMetrics, ...]
    mean_faithfulness: float | None
    mean_answer_relevancy: float | None
    mean_context_precision: float | None
    mean_context_recall: float | None


def load_generation_golden_set(path: Path) -> list[GenerationGoldenQuery]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("generation golden set must contain a non-empty queries list")

    golden: list[GenerationGoldenQuery] = []
    seen_ids: set[str] = set()
    for entry in queries:
        if not isinstance(entry, dict):
            raise ValueError("each generation golden query must be an object")
        query_id = str(entry.get("id", "")).strip()
        question = str(entry.get("question", "")).strip()
        ground_truth = str(entry.get("ground_truth", "")).strip()
        if not query_id or not question or not ground_truth:
            raise ValueError(f"invalid generation golden query entry: {entry!r}")
        if query_id in seen_ids:
            raise ValueError(f"duplicate generation golden query id: {query_id}")
        seen_ids.add(query_id)
        golden.append(
            GenerationGoldenQuery(
                id=query_id,
                question=question,
                ground_truth=ground_truth,
            )
        )
    return golden


def format_ragas_answer(result: RagEstimationResult) -> str:
    """Natural-language answer for RAGAS metrics (not raw JSON)."""

    lines = [result.summary.strip()]
    for item in result.line_items:
        status = "grounded" if item.grounded else "ungrounded"
        lines.append(
            f"- {item.component}: {item.hours:g}h ({status}) — {item.rationale.strip()}"
        )
    if result.insufficient_context:
        lines.append("(insufficient retrieval context)")
    lines.append(f"Total: {result.total_hours:g}h {result.currency}")
    return "\n".join(lines)


def build_ragas_records(samples: Sequence[RagasSample]) -> list[dict[str, Any]]:
    """Shape samples into RAGAS-compatible record dicts."""

    return [
        {
            "question": sample.question,
            "answer": sample.answer,
            "contexts": list(sample.contexts),
            "ground_truth": sample.ground_truth,
        }
        for sample in samples
    ]


def _finite_mean(values: Sequence[float]) -> float | None:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return None
    return statistics.mean(finite)


def _metric_is_finite(value: float) -> bool:
    return math.isfinite(value)


def _format_metric_cell(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.3f}"


def _json_metric_value(value: float) -> float | None:
    return value if math.isfinite(value) else None


def summarize_generation_metrics(
    per_query: Sequence[QueryGenerationMetrics],
) -> GenerationMetrics:
    if not per_query:
        raise ValueError("per_query must not be empty")

    return GenerationMetrics(
        per_query=tuple(per_query),
        mean_faithfulness=_finite_mean(item.faithfulness for item in per_query),
        mean_answer_relevancy=_finite_mean(item.answer_relevancy for item in per_query),
        mean_context_precision=_finite_mean(item.context_precision for item in per_query),
        mean_context_recall=_finite_mean(item.context_recall for item in per_query),
    )


def render_generation_comparison_markdown(metrics: GenerationMetrics) -> str:
    lines = [
        "# Generation quality comparison (RAGAS)",
        "",
        "| Query | Faithfulness | Answer relevancy | Context precision | Context recall |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in metrics.per_query:
        lines.append(
            "| {id} | {faithfulness} | {answer_relevancy} | {context_precision} | {context_recall} |".format(
                id=row.query_id,
                faithfulness=_format_metric_cell(row.faithfulness),
                answer_relevancy=_format_metric_cell(row.answer_relevancy),
                context_precision=_format_metric_cell(row.context_precision),
                context_recall=_format_metric_cell(row.context_recall),
            )
        )
    lines.append(
        "| **mean** | {faithfulness} | {answer_relevancy} | {context_precision} | {context_recall} |".format(
            faithfulness=_format_metric_cell(metrics.mean_faithfulness),
            answer_relevancy=_format_metric_cell(metrics.mean_answer_relevancy),
            context_precision=_format_metric_cell(metrics.mean_context_precision),
            context_recall=_format_metric_cell(metrics.mean_context_recall),
        )
    )
    return "\n".join(lines) + "\n"


def _metric_columns(metrics: GenerationMetrics) -> tuple[tuple[str, float | None], ...]:
    return (
        ("faithfulness", metrics.mean_faithfulness),
        ("answer_relevancy", metrics.mean_answer_relevancy),
        ("context_precision", metrics.mean_context_precision),
        ("context_recall", metrics.mean_context_recall),
    )


def _non_finite_metric_names(metrics: GenerationMetrics) -> list[str]:
    accessors = (
        ("faithfulness", lambda row: row.faithfulness),
        ("answer_relevancy", lambda row: row.answer_relevancy),
        ("context_precision", lambda row: row.context_precision),
        ("context_recall", lambda row: row.context_recall),
    )
    broken: list[str] = []
    for name, accessor in accessors:
        if not any(_metric_is_finite(accessor(row)) for row in metrics.per_query):
            broken.append(name)
    return broken


def render_quality_note(metrics: GenerationMetrics) -> str:
    usable_metrics = [
        (name, mean)
        for name, mean in _metric_columns(metrics)
        if mean is not None and math.isfinite(mean)
    ]
    broken_metrics = _non_finite_metric_names(metrics)

    parts: list[str] = []
    if broken_metrics:
        joined = ", ".join(f"`{name}`" for name in broken_metrics)
        parts.append(
            f"The following metric columns had no finite per-query scores and were skipped in means: {joined}."
        )

    if not usable_metrics:
        return (
            " ".join(parts)
            + " No aggregate metric means could be computed from this run. "
            "Treat the 5-query baseline as directional only until the golden set grows."
        ).strip()

    weakest_metric_name, weakest_mean = min(usable_metrics, key=lambda item: item[1])
    weakest_query = min(
        metrics.per_query,
        key=lambda row: {
            "faithfulness": row.faithfulness,
            "answer_relevancy": row.answer_relevancy,
            "context_precision": row.context_precision,
            "context_recall": row.context_recall,
        }[weakest_metric_name],
    )
    parts.append(
        f"The weakest aggregate metric in this baseline is **{weakest_metric_name}** "
        f"(mean {weakest_mean:.3f}). Query `{weakest_query.query_id}` scored lowest on that "
        f"axis and is the best candidate for prompt or retrieval tuning. Treat the 5-query "
        f"baseline as directional only until the golden set grows."
    )
    return " ".join(parts)


def metrics_to_json(metrics: GenerationMetrics) -> dict[str, Any]:
    return {
        "mean": {
            "faithfulness": metrics.mean_faithfulness,
            "answer_relevancy": metrics.mean_answer_relevancy,
            "context_precision": metrics.mean_context_precision,
            "context_recall": metrics.mean_context_recall,
        },
        "per_query": [
            {
                "query_id": row.query_id,
                "faithfulness": _json_metric_value(row.faithfulness),
                "answer_relevancy": _json_metric_value(row.answer_relevancy),
                "context_precision": _json_metric_value(row.context_precision),
                "context_recall": _json_metric_value(row.context_recall),
            }
            for row in metrics.per_query
        ],
    }


def extract_per_query_metrics(
    evaluate_result: Any,
    *,
    query_ids: Sequence[str],
) -> list[QueryGenerationMetrics]:
    """Map a RAGAS evaluate result object to per-query metric rows."""

    rows: list[QueryGenerationMetrics] = []
    for index, query_id in enumerate(query_ids):
        rows.append(
            QueryGenerationMetrics(
                query_id=query_id,
                faithfulness=float(_metric_value(evaluate_result, "faithfulness", index)),
                answer_relevancy=float(_metric_value(evaluate_result, "answer_relevancy", index)),
                context_precision=float(_metric_value(evaluate_result, "context_precision", index)),
                context_recall=float(_metric_value(evaluate_result, "context_recall", index)),
            )
        )
    return rows


def _metric_value(result: Any, metric_name: str, index: int) -> float:
    if hasattr(result, "to_pandas"):
        frame = result.to_pandas()
        return float(frame.iloc[index][metric_name])
    scores = getattr(result, metric_name, None)
    if isinstance(scores, list):
        return float(scores[index])
    raise ValueError(f"unsupported RAGAS result shape for metric {metric_name!r}")


def validate_generation_preflight(
    *,
    settings: Any,
    corpus: Any | None,
    alembic_revision: str | None,
) -> tuple[bool, tuple[str, ...]]:
    """Preflight checks for offline RAGAS generation eval."""

    from app.embedding_pipeline.retrieval_eval import REQUIRED_ALEMBIC_REVISION

    errors: list[str] = []
    try:
        import ragas  # noqa: F401
    except ImportError as exc:
        errors.append(f"ragas is not importable: {exc}")
    if not settings.openai_api_key.strip():
        errors.append("OPENAI_API_KEY is required for RAGAS generation evaluation.")
    if not settings.database_url.strip():
        errors.append("DATABASE_URL is required for generation evaluation.")
    if alembic_revision != REQUIRED_ALEMBIC_REVISION:
        errors.append(
            f"Alembic revision must be {REQUIRED_ALEMBIC_REVISION}; got {alembic_revision!r}."
        )
    if corpus is None or corpus.chunk_count == 0:
        errors.append("Corpus is empty; ingest budget chunks before evaluation.")
    return (not errors, tuple(errors))


def run_ragas_evaluation(
    records: Sequence[dict[str, Any]],
    *,
    judge_model: str,
    embedding_model: str,
    api_key: str,
) -> Any:
    """Run RAGAS metrics over shaped records (slow; requires live OpenAI)."""

    from datasets import Dataset
    from openai import OpenAI
    from ragas import evaluate
    from ragas.embeddings import OpenAIEmbeddings
    from ragas.llms import llm_factory
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    client = OpenAI(api_key=api_key)
    dataset = Dataset.from_list(list(records))
    llm = llm_factory(judge_model, provider="openai", client=client)
    embeddings = OpenAIEmbeddings(model=embedding_model, client=client)
    return evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        embeddings=embeddings,
        show_progress=True,
    )
