"""Per-task hours estimation via historical task vector search (feature-062)."""

from __future__ import annotations

import asyncio
import logging
import statistics
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.retrieval_debug_schemas import RetrievalMetadataFilters
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.schemas.rag_task_hours import (
    TaskHoursEstimateView,
    TaskHoursModuleInput,
    TaskHoursResultView,
    TaskHoursTaskInput,
    TaskNeighborView,
)

logger = logging.getLogger(__name__)

_HISTORICAL_TASK_CHUNK_TYPE = "historical_task"
_WEIGHT_EPS = 1e-3


def compose_task_search_text(module: str, name: str, description: str | None) -> str:
    parts: list[str] = []
    if module:
        parts.append(f"Module: {module}")
    parts.append(f"Task: {name}")
    if description:
        parts.append(description)
    return "\n".join(parts)


def consensus_hours(neighbors: list[tuple[int, float]]) -> tuple[int, float, float]:
    """Distance-weighted consensus over ``(hours, distance)`` neighbours."""

    if not neighbors:
        raise ValueError("neighbors must be non-empty")

    weights = [1.0 / (_WEIGHT_EPS + dist) for _hours, dist in neighbors]
    total_w = sum(weights)
    hours_values = [hours for hours, _dist in neighbors]

    weighted_hours = sum(w * h for w, (h, _d) in zip(weights, neighbors)) / total_w
    weighted_similarity = (
        sum(w * max(0.0, 1.0 - dist) for w, (_h, dist) in zip(weights, neighbors)) / total_w
    )

    mean_hours = statistics.fmean(hours_values)
    if len(hours_values) > 1 and mean_hours > 0:
        dispersion = statistics.pstdev(hours_values) / mean_hours
    else:
        dispersion = 0.0

    reliability = weighted_similarity * (1.0 - min(dispersion, 1.0))
    reliability = max(0.0, min(1.0, reliability))
    return round(weighted_hours), round(reliability, 3), round(dispersion, 3)


def _estimated_hours_from_metadata(metadata: dict[str, object]) -> int | None:
    raw = metadata.get("estimated_hours")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class _TaskNeighbor:
    chunk_id: int
    budget_id: str | None
    estimated_hours: int
    distance: float


async def _search_historical_neighbors(
    session: AsyncSession,
    *,
    embedder: OpenAIEmbedder,
    search_text: str,
    top_k: int,
    distance_threshold: float,
    repository: SemanticSearchRepository,
) -> list[_TaskNeighbor]:
    query_vector = await embedder.embed_one(search_text)
    filters = RetrievalMetadataFilters(chunk_types=[_HISTORICAL_TASK_CHUNK_TYPE])
    results = await repository.search_chunks(
        session,
        query_vector=query_vector,
        k=top_k,
        filters=filters,
    )
    neighbors: list[_TaskNeighbor] = []
    for row in results:
        if row.distance > distance_threshold:
            continue
        hours = _estimated_hours_from_metadata(dict(row.metadata))
        if hours is None:
            continue
        budget_id = row.metadata.get("budget_id")
        neighbors.append(
            _TaskNeighbor(
                chunk_id=row.chunk_id,
                budget_id=str(budget_id) if budget_id is not None else None,
                estimated_hours=hours,
                distance=row.distance,
            )
        )
    return neighbors


async def estimate_one_task(
    session: AsyncSession,
    *,
    module: str,
    name: str,
    description: str | None,
    embedder: OpenAIEmbedder,
    settings: Settings,
    repository: SemanticSearchRepository,
    top_k: int | None = None,
    distance_threshold: float | None = None,
) -> TaskHoursEstimateView:
    k = top_k if top_k is not None else settings.task_hours_top_k
    threshold = (
        distance_threshold if distance_threshold is not None else settings.task_hours_distance_threshold
    )
    search_text = compose_task_search_text(module, name, description)
    neighbors = await _search_historical_neighbors(
        session,
        embedder=embedder,
        search_text=search_text,
        top_k=k,
        distance_threshold=threshold,
        repository=repository,
    )
    if not neighbors:
        return TaskHoursEstimateView(module=module, task=name, has_match=False)

    hours, reliability, dispersion = consensus_hours(
        [(n.estimated_hours, n.distance) for n in neighbors]
    )
    return TaskHoursEstimateView(
        module=module,
        task=name,
        estimated_hours=hours,
        reliability=reliability,
        dispersion=dispersion,
        has_match=True,
        neighbors=[
            TaskNeighborView(
                chunk_id=n.chunk_id,
                budget_id=n.budget_id,
                estimated_hours=n.estimated_hours,
                distance=n.distance,
            )
            for n in neighbors
        ],
    )


async def estimate_all_tasks(
    session: AsyncSession,
    modules: list[TaskHoursModuleInput],
    *,
    embedder: OpenAIEmbedder,
    settings: Settings,
    repository: SemanticSearchRepository,
    top_k: int | None = None,
    distance_threshold: float | None = None,
) -> TaskHoursResultView:
    coros = [
        estimate_one_task(
            session,
            module=module.name,
            name=task.name,
            description=task.description,
            embedder=embedder,
            settings=settings,
            repository=repository,
            top_k=top_k,
            distance_threshold=distance_threshold,
        )
        for module in modules
        for task in module.tasks
    ]
    estimates = await asyncio.gather(*coros)
    matched = sum(1 for estimate in estimates if estimate.has_match)
    logger.info(
        "task_hours_done",
        extra={
            "tasks": len(estimates),
            "matched": matched,
            "flagged": len(estimates) - matched,
        },
    )
    return TaskHoursResultView(tasks=list(estimates))
