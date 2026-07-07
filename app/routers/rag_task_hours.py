"""Per-task hours API (feature-062)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db_session
from app.deps import get_request_id
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.middleware.rate_limiting import conditional_rate_limit
from app.middleware.security import require_estimate_key
from app.schemas.rag_task_hours import TaskHoursRequest, TaskHoursResultView
from app.services.rag_task_hours import estimate_all_tasks

router = APIRouter(tags=["rag-task-hours"])
logger = logging.getLogger(__name__)
_search_repository = SemanticSearchRepository()


def get_embedder(settings: Annotated[Settings, Depends(get_settings)]) -> OpenAIEmbedder:
    return OpenAIEmbedder(settings)


@router.post(
    "/estimate/rag/tasks/hours",
    response_model=TaskHoursResultView,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("30/minute")
async def estimate_task_hours(
    request: Request,
    payload: TaskHoursRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    embedder: Annotated[OpenAIEmbedder, Depends(get_embedder)],
) -> TaskHoursResultView:
    request_id = get_request_id(request)
    try:
        return await estimate_all_tasks(
            session,
            payload.modules,
            embedder=embedder,
            settings=settings,
            repository=_search_repository,
            top_k=payload.top_k,
            distance_threshold=payload.distance_threshold,
        )
    except Exception as exc:
        logger.error(
            "task_hours_failed",
            extra={"request_id": request_id, "error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to estimate task hours.",
        ) from exc
