"""``/api/v1/estimate/graph`` — multi-agent estimation flow (Session 13).

Three verbs over one ``thread_id`` (= ``estimation_id``):

* ``POST /graph`` — START until the first human gate (or completion).
* ``POST /graph/{estimation_id}/resume`` — RESUME with the human decision; 409 if
  nothing is pending.
* ``GET /graph/{estimation_id}/state`` — read the current snapshot; 404 if unknown.

Auth reuses ``ESTIMATE_API_KEY``. Graph/LLM failures → 502. When the graph failed
to build at startup (``app.state.graph is None``) → 503.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from langgraph.types import Command

from app.deps import get_request_id
from app.middleware.rate_limiting import conditional_rate_limit
from app.middleware.security import require_estimate_key
from app.schemas.graph_estimation import (
    GraphEstimateRequest,
    GraphResumeRequest,
    GraphRunState,
    PendingGate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/estimate", tags=["estimate-graph"])


def _require_graph(request: Request, request_id: str):
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        logger.error("graph_unavailable", extra={"request_id": request_id})
        raise HTTPException(
            status_code=503,
            detail="Estimation graph is not available.",
        )
    return graph


def _build_run_state(estimation_id: str, snapshot) -> GraphRunState:
    """Turn a LangGraph ``StateSnapshot`` into the public ``GraphRunState``."""
    values = snapshot.values or {}
    paused = bool(snapshot.next)
    pending_gate = None
    interrupts = getattr(snapshot, "interrupts", None) or ()
    if paused and interrupts:
        gate_value = interrupts[0].value or {}
        pending_gate = PendingGate(
            gate=gate_value.get("gate", "unknown"),
            estimation_id=estimation_id,
            payload={
                k: v for k, v in gate_value.items() if k not in ("gate", "estimation_id")
            },
        )
    return GraphRunState(
        estimation_id=estimation_id,
        state="paused" if paused else "completed",
        pending_gate=pending_gate,
        complexity=values.get("complexity"),
        structure=values.get("structure"),
        task_hours=values.get("task_hours") or [],
        estimate=values.get("estimate"),
        analysis_report=values.get("analysis_report"),
        proposal=values.get("proposal"),
        status=values.get("status"),
        errors=values.get("errors") or [],
    )


@router.post(
    "/graph",
    response_model=GraphRunState,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("10/minute")
async def estimate_graph(request: Request, payload: GraphEstimateRequest) -> GraphRunState:
    """START the multi-agent flow; runs to the first human gate."""
    request_id = get_request_id(request)
    graph = _require_graph(request, request_id)

    estimation_id = payload.estimation_id or str(uuid4())
    config = {"configurable": {"thread_id": estimation_id}}
    try:
        logger.info(
            "graph_estimate_start",
            extra={"request_id": request_id, "estimation_id": estimation_id},
        )
        await graph.ainvoke(
            {"transcript": payload.transcript, "estimation_id": estimation_id},
            config,
        )
        snapshot = await graph.aget_state(config)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — any node/LLM failure → 502
        logger.error(
            "graph_estimate_failed",
            extra={
                "request_id": request_id,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to produce an estimate.",
        ) from exc

    return _build_run_state(estimation_id, snapshot)


@router.post(
    "/graph/{estimation_id}/resume",
    response_model=GraphRunState,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("10/minute")
async def resume_graph(
    request: Request,
    estimation_id: str,
    payload: GraphResumeRequest,
) -> GraphRunState:
    """RESUME a paused run with the human's decision."""
    request_id = get_request_id(request)
    graph = _require_graph(request, request_id)
    config = {"configurable": {"thread_id": estimation_id}}

    snapshot = await graph.aget_state(config)
    if not snapshot.next:
        raise HTTPException(
            status_code=409,
            detail=(
                "No pending human gate for this estimation_id "
                "(already completed or unknown)."
            ),
        )

    try:
        logger.info(
            "graph_estimate_resume",
            extra={"request_id": request_id, "estimation_id": estimation_id},
        )
        await graph.ainvoke(Command(resume=payload.decision), config)
        snapshot = await graph.aget_state(config)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — any node/LLM failure → 502
        logger.error(
            "graph_estimate_resume_failed",
            extra={
                "request_id": request_id,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to resume the estimate.",
        ) from exc

    return _build_run_state(estimation_id, snapshot)


@router.get(
    "/graph/{estimation_id}/state",
    response_model=GraphRunState,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("60/minute")
async def graph_state(request: Request, estimation_id: str) -> GraphRunState:
    """Read the current snapshot of a run (pending gate + artifacts)."""
    request_id = get_request_id(request)
    graph = _require_graph(request, request_id)
    config = {"configurable": {"thread_id": estimation_id}}
    snapshot = await graph.aget_state(config)
    if not snapshot.created_at and not snapshot.values:
        raise HTTPException(status_code=404, detail="Unknown estimation_id.")
    return _build_run_state(estimation_id, snapshot)
