"""HTTP API for simplified session-based estimation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.guardrails.exceptions import GuardrailViolationError
from app.schemas.simplified_session import (
    AttachmentProcessingStatus,
    SessionDetailResponse,
    SessionEstimateRequest,
    SessionEstimateResponse,
    SessionListItem,
    SessionListResponse,
)
from app.services.attachment_errors import AttachmentError
from app.services.estimation_v2_response_builder import assemble_estimation_v2_response
from app.services.llm_chain import build_provider_chain
from app.services.llm_service import (
    DomainGuardrailError,
    EXAMPLES_VERSION,
    PROMPT_VERSION,
    EstimationService,
)
from app.services.simplified_session_estimation_service import (
    SessionNotFoundError,
    SessionSubmitValidationError,
    SimplifiedSessionEstimationService,
)
from app.services.sessions import session_display_label, session_store

router = APIRouter(tags=["sessions"])
logger = logging.getLogger(__name__)


def get_estimation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimationService:
    return EstimationService(settings, build_provider_chain(settings))


def get_simplified_session_service(
    settings: Annotated[Settings, Depends(get_settings)],
    estimation_service: Annotated[EstimationService, Depends(get_estimation_service)],
) -> SimplifiedSessionEstimationService:
    return SimplifiedSessionEstimationService(settings, estimation_service, session_store)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session() -> dict[str, str]:
    """Create an empty in-memory session."""

    session = session_store.create_session()
    return {"session_id": session.session_id}


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions() -> SessionListResponse:
    """List in-memory sessions for the UI history sidebar (last 30 days)."""

    items = [
        SessionListItem(
            session_id=session.session_id,
            label=session_display_label(session),
            updated_at=session.updated_at,
            submit_count=session.submit_count,
        )
        for session in session_store.list_sessions()
    ]
    return SessionListResponse(sessions=items)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str) -> SessionDetailResponse:
    """Return stored payload and metadata snapshot for session restore."""

    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    metadata = (
        session.last_derived_metadata.model_dump(mode="json")
        if session.last_derived_metadata is not None
        else None
    )
    attachment_statuses: list[AttachmentProcessingStatus] = []
    for item in session.last_attachment_statuses:
        if isinstance(item, AttachmentProcessingStatus):
            attachment_statuses.append(item)
        else:
            attachment_statuses.append(AttachmentProcessingStatus.model_validate(item))
    return SessionDetailResponse(
        session_id=session.session_id,
        input_payload=session.last_normalized_payload,
        project_metadata=metadata,
        estimate=session.last_estimate,
        warnings=list(session.last_warnings),
        attachments=attachment_statuses,
        submit_count=session.submit_count,
    )


@router.post(
    "/sessions/{session_id}/estimate",
    response_model=SessionEstimateResponse,
)
async def estimate_in_session(
    session_id: str,
    body: SessionEstimateRequest,
    service: Annotated[SimplifiedSessionEstimationService, Depends(get_simplified_session_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionEstimateResponse:
    """Run one simplified transcript-centered estimation submit."""

    start = perf_counter()
    request_id = f"sess_{uuid4().hex[:12]}"
    try:
        submit = await service.run_submit(session_id, body, request_id=request_id)
    except DomainGuardrailError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code,
                "message": str(exc),
            },
        ) from exc
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SessionSubmitValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_session_submit", "message": str(exc)},
        ) from exc
    except AttachmentError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except GuardrailViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.reason_code,
                "message": exc.user_message,
                "audit_id": exc.audit_id,
            },
        ) from exc

    outcome = submit.pipeline
    if outcome.bundle is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": outcome.reason_code or "error",
                "message": outcome.user_message or "Unable to complete structured estimation.",
                "audit_id": outcome.audit_id,
            },
        )

    finished_at = datetime.now(UTC)
    latency_ms = int((perf_counter() - start) * 1000)
    estimate = assemble_estimation_v2_response(
        outcome.bundle,
        evaluate=True,
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

    estimate_payload = estimate.model_dump(mode="json")
    stored = session_store.get_session(session_id)
    if stored is not None:
        stored.last_estimate = estimate_payload
        stored.last_warnings = list(submit.warnings)

    return SessionEstimateResponse(
        session_id=session_id,
        input_payload=submit.normalized_payload,
        project_metadata=submit.derived_metadata,
        estimate=estimate_payload,
        warnings=submit.warnings,
        attachments=submit.attachment_statuses,
    )
