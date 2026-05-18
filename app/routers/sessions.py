"""HTTP API for conversational estimation sessions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.schemas.estimations import EstimateResponse, UsageView
from app.schemas.session_estimation import SessionEstimateRequest, SessionSummary
from app.services.conversational_estimation_service import (
    ConversationalEstimationService,
    SessionNotFoundError,
)
from app.services.estimate_response_builder import assemble_estimate_response
from app.services.llm_chain import build_provider_chain
from app.services.llm_service import (
    EXAMPLES_VERSION,
    PROMPT_VERSION,
    DomainGuardrailError,
    EstimationError,
    EstimationService,
)
from app.services.metadata_extractor import MetadataExtractionError
from app.services.observability.bootstrap import get_observability
from app.services.observability.types import TelemetryContext
from app.services.session_summary import session_to_summary
from app.services.sessions import session_store

router = APIRouter(tags=["sessions"])
logger = logging.getLogger(__name__)

SESSION_CREATE_TRACE = "estimator.api.v1.session_create"
SESSION_LIST_TRACE = "estimator.api.v1.session_list"
SESSION_ESTIMATE_TRACE = "estimator.api.v1.session_estimate"


def get_estimation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimationService:
    return EstimationService(settings, build_provider_chain(settings))


def get_conversational_service(
    settings: Annotated[Settings, Depends(get_settings)],
    estimation_service: Annotated[EstimationService, Depends(get_estimation_service)],
) -> ConversationalEstimationService:
    return ConversationalEstimationService(settings, estimation_service, session_store)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session() -> dict[str, str]:
    """Create an empty in-memory conversational session."""

    request_id = f"sess_{uuid4().hex[:12]}"
    observability = get_observability()
    observability.set_prompt_context(
        prompt_version=PROMPT_VERSION,
        examples_version=EXAMPLES_VERSION,
    )
    session = session_store.create_session()
    with observability.start_trace(
        SESSION_CREATE_TRACE,
        context=TelemetryContext(
            request_id=request_id,
            feature="estimation",
            session_id=session.session_id,
            tags=["feature:estimation", "endpoint:api_v1_session_create"],
        ),
    ):
        observability.set_http_status(status.HTTP_201_CREATED)
        return {"session_id": session.session_id}


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions() -> list[SessionSummary]:
    """List all in-memory sessions (most recently updated first)."""

    request_id = f"sess_{uuid4().hex[:12]}"
    observability = get_observability()
    trace_context = TelemetryContext(
        request_id=request_id,
        feature="estimation",
        session_id=None,
        tags=["feature:estimation", "endpoint:api_v1_session_list"],
    )
    with observability.start_trace(SESSION_LIST_TRACE, context=trace_context):
        summaries = [session_to_summary(s) for s in session_store.list_sessions()]
        observability.set_http_status(status.HTTP_200_OK)
        return summaries


@router.post(
    "/sessions/{session_id}/estimate",
    response_model=EstimateResponse,
    response_model_exclude_none=True,
)
async def estimate_in_session(
    session_id: str,
    body: SessionEstimateRequest,
    service: Annotated[ConversationalEstimationService, Depends(get_conversational_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimateResponse:
    """Run one conversational estimation turn within an existing session."""

    start = perf_counter()
    request_id = f"sess_{uuid4().hex[:12]}"
    try:
        turn = await service.run_turn(session_id, body.user_message)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DomainGuardrailError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except MetadataExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except EstimationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    outcome = turn.estimation
    finished_at = datetime.now(UTC)
    latency_ms = int((perf_counter() - start) * 1000)

    response, _ = assemble_estimate_response(
        outcome,
        evaluate=False,
        dev_mode=settings.dev_mode,
        stats_log_enabled=False,
        request_id=request_id,
        finished_at=finished_at,
        latency_ms=latency_ms,
    )
    return response
