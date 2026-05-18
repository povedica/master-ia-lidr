"""HTTP API for guided-form estimation sessions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.guardrails.exceptions import GuardrailViolationError
from app.schemas.estimation_request import EstimationRequest
from app.schemas.estimation_response import EstimationResponse
from app.schemas.session_estimation import SessionSummary
from app.services.attachment_errors import AttachmentError
from app.services.estimation_v2_response_builder import assemble_estimation_v2_response
from app.services.llm_chain import build_provider_chain
from app.services.llm_service import (
    EXAMPLES_VERSION,
    PROMPT_VERSION,
    EstimationService,
)
from app.services.observability.bootstrap import get_observability
from app.services.observability.types import TelemetryContext
from app.services.session_estimation_service import SessionEstimationService, SessionNotFoundError
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


def get_session_estimation_service(
    settings: Annotated[Settings, Depends(get_settings)],
    estimation_service: Annotated[EstimationService, Depends(get_estimation_service)],
) -> SessionEstimationService:
    return SessionEstimationService(settings, estimation_service, session_store)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session() -> dict[str, str]:
    """Create an empty in-memory session."""

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
    with observability.start_trace(
        SESSION_LIST_TRACE,
        context=TelemetryContext(
            request_id=request_id,
            feature="estimation",
            session_id=None,
            tags=["feature:estimation", "endpoint:api_v1_session_list"],
        ),
    ):
        summaries = [session_to_summary(s) for s in session_store.list_sessions()]
        observability.set_http_status(status.HTTP_200_OK)
        return summaries


@router.post(
    "/sessions/{session_id}/estimate",
    response_model=EstimationResponse,
    response_model_exclude_none=True,
)
async def estimate_in_session(
    session_id: str,
    body: EstimationRequest,
    service: Annotated[SessionEstimationService, Depends(get_session_estimation_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimationResponse:
    """Run one guided-form estimation submit within an existing session."""

    start = perf_counter()
    request_id = f"sess_{uuid4().hex[:12]}"
    observability = get_observability()
    observability.set_prompt_context(
        prompt_version=PROMPT_VERSION,
        examples_version=EXAMPLES_VERSION,
    )
    trace_context = TelemetryContext(
        request_id=request_id,
        feature="estimation",
        session_id=session_id,
        tags=["feature:estimation", "endpoint:api_v1_session_estimate"],
        metadata={
            "prompt_version": PROMPT_VERSION,
            "examples_version": EXAMPLES_VERSION,
        },
    )

    with observability.start_trace(SESSION_ESTIMATE_TRACE, context=trace_context):
        try:
            with observability.start_span("session.load"):
                pass
            return await _execute_session_estimate(
                session_id=session_id,
                body=body,
                service=service,
                settings=settings,
                request_id=request_id,
                started_at_perf=start,
                observability=observability,
            )
        except SessionNotFoundError as exc:
            observability.set_http_status(status.HTTP_404_NOT_FOUND)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except AttachmentError as exc:
            observability.set_http_status(exc.status_code)
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        except GuardrailViolationError as exc:
            observability.set_http_status(status.HTTP_422_UNPROCESSABLE_CONTENT)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": exc.reason_code,
                    "message": exc.user_message,
                    "audit_id": exc.audit_id,
                },
            ) from exc


async def _execute_session_estimate(
    *,
    session_id: str,
    body: EstimationRequest,
    service: SessionEstimationService,
    settings: Settings,
    request_id: str,
    started_at_perf: float,
    observability,
) -> EstimationResponse:
    with observability.start_span("attachment.extract"):
        pass
    with observability.start_span("prompt.compose"):
        pass

    with observability.start_span("estimator.estimate"):
        submit = await service.run_submit(session_id, body, request_id=request_id)

    outcome = submit.pipeline
    if outcome.bundle is None:
        observability.set_http_status(status.HTTP_503_SERVICE_UNAVAILABLE)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": outcome.reason_code or "error",
                "message": outcome.user_message or "Unable to complete structured estimation.",
                "audit_id": outcome.audit_id,
            },
        )

    with observability.start_span("metadata.sync"):
        pass

    finished_at = datetime.now(UTC)
    latency_ms = int((perf_counter() - started_at_perf) * 1000)
    response = assemble_estimation_v2_response(
        outcome.bundle,
        evaluate=body.evaluate,
        dev_mode=settings.dev_mode,
        request_id=request_id,
        finished_at=finished_at,
        latency_ms=latency_ms,
        pipeline_final_status=outcome.final_status,
        pipeline_reason_code=outcome.reason_code,
        pipeline_user_message=outcome.user_message,
        pipeline_technical_message=outcome.technical_message,
        pipeline_audit_id=outcome.audit_id,
        pipeline_safe_to_cache=outcome.safe_to_cache,
        pipeline_safe_to_display=outcome.safe_to_display,
        pipeline_cached=outcome.cached,
        pipeline_cache_score=outcome.cache_score,
        pipeline_cache_bucket=outcome.cache_bucket,
        pipeline_cache_miss_reason=outcome.cache_miss_reason,
    )
    observability.set_http_status(status.HTTP_200_OK)
    return response
