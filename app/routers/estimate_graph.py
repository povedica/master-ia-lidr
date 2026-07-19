"""``/api/v1/estimate/graph`` — multi-agent estimation flow (Session 13).

Three blocking verbs over one ``thread_id`` (= ``estimation_id``):

* ``POST /graph`` — START until the first human gate (or completion).
* ``POST /graph/{estimation_id}/resume`` — RESUME with the human decision; 409 if
  nothing is pending.
* ``GET /graph/{estimation_id}/state`` — read the current snapshot; 404 if unknown.

Plus the live "watch the agents work" surface (Step 8):

* ``POST /graph/stream`` — START in the background (202); poll ``/progress``.
* ``POST /graph/{id}/resume-stream`` — RESUME in the background (202).
* ``GET /graph/{id}/progress`` — ``running`` | ``paused`` | ``completed`` + activity.
* ``POST /graph/{id}/proposal`` — on-demand commercial proposal (no graph re-run).

Auth reuses ``ESTIMATE_API_KEY``. Graph/LLM failures → 502. When the graph failed
to build at startup (``app.state.graph is None``) → 503.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from langgraph.types import Command

from app.config import Settings, get_settings
from app.deps import get_graph_activity, get_request_id
from app.middleware.rate_limiting import conditional_rate_limit
from app.middleware.security import require_estimate_key
from app.schemas.graph_estimation import (
    ActivityEntry,
    GraphEstimateRequest,
    GraphProgress,
    GraphProposalResponse,
    GraphResumeRequest,
    GraphRunState,
    PendingGate,
)
from app.services.estimation_graph.activity import GraphActivityLog, describe_node
from app.services.estimation_graph.agents.proposal import build_proposal
from app.services.estimation_graph.personas import persona_for

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


def _progress_state(snapshot) -> str:
    """running (mid-leg) | paused (at a gate) | completed (END)."""
    if not getattr(snapshot, "next", None):
        return "completed"
    interrupts = getattr(snapshot, "interrupts", None) or ()
    return "paused" if interrupts else "running"


async def _stream_graph(
    *,
    graph,
    activity: GraphActivityLog,
    payload,
    config: dict,
    estimation_id: str,
    request_id: str,
) -> None:
    """BackgroundTask body: drive the graph with ``astream`` and log each node."""
    try:
        async for chunk in graph.astream(payload, config, stream_mode="updates"):
            for node_name, update in chunk.items():
                for line in describe_node(node_name, update):
                    activity.append(
                        estimation_id,
                        node=line["node"],
                        label=line["label"],
                        message=line["message"],
                    )
    except Exception as exc:  # noqa: BLE001 — surface failure in the feed
        logger.error(
            "graph_stream_failed",
            extra={
                "request_id": request_id,
                "estimation_id": estimation_id,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            },
        )
        activity.append(
            estimation_id,
            node="error",
            label="Error",
            message=str(exc)[:200],
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


@router.post(
    "/graph/stream",
    response_model=GraphProgress,
    status_code=202,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("10/minute")
async def estimate_graph_stream(
    request: Request,
    payload: GraphEstimateRequest,
    background: BackgroundTasks,
    activity: GraphActivityLog = Depends(get_graph_activity),
) -> GraphProgress:
    """START the flow in the background; returns 202 immediately, poll ``/progress``."""
    request_id = get_request_id(request)
    graph = _require_graph(request, request_id)
    estimation_id = payload.estimation_id or str(uuid4())
    config = {"configurable": {"thread_id": estimation_id}}

    activity.reset(estimation_id)
    background.add_task(
        _stream_graph,
        graph=graph,
        activity=activity,
        payload={"transcript": payload.transcript, "estimation_id": estimation_id},
        config=config,
        estimation_id=estimation_id,
        request_id=request_id,
    )
    logger.info(
        "graph_stream_started",
        extra={"request_id": request_id, "estimation_id": estimation_id},
    )
    return GraphProgress(estimation_id=estimation_id, state="running", activity=[])


@router.post(
    "/graph/{estimation_id}/resume-stream",
    response_model=GraphProgress,
    status_code=202,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("10/minute")
async def resume_graph_stream(
    request: Request,
    estimation_id: str,
    payload: GraphResumeRequest,
    background: BackgroundTasks,
    activity: GraphActivityLog = Depends(get_graph_activity),
) -> GraphProgress:
    """RESUME a paused run in the background; returns 202, poll ``/progress``."""
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

    background.add_task(
        _stream_graph,
        graph=graph,
        activity=activity,
        payload=Command(resume=payload.decision),
        config=config,
        estimation_id=estimation_id,
        request_id=request_id,
    )
    logger.info(
        "graph_resume_stream_started",
        extra={"request_id": request_id, "estimation_id": estimation_id},
    )
    return GraphProgress(estimation_id=estimation_id, state="running", activity=[])


@router.get(
    "/graph/{estimation_id}/progress",
    response_model=GraphProgress,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("120/minute")
async def graph_progress(
    request: Request,
    estimation_id: str,
    activity: GraphActivityLog = Depends(get_graph_activity),
) -> GraphProgress:
    """Poll a background run: current state + activity feed."""
    request_id = get_request_id(request)
    graph = _require_graph(request, request_id)
    config = {"configurable": {"thread_id": estimation_id}}
    snapshot = await graph.aget_state(config)

    entries = [ActivityEntry(**e) for e in activity.read(estimation_id)]
    # No 404: right after START the first checkpoint may not exist yet.
    run_state = _build_run_state(estimation_id, snapshot)
    data = run_state.model_dump()
    data["state"] = _progress_state(snapshot)
    data["activity"] = entries
    return GraphProgress(**data)


@router.post(
    "/graph/{estimation_id}/proposal",
    response_model=GraphProposalResponse,
    dependencies=[Depends(require_estimate_key)],
)
@conditional_rate_limit("10/minute")
async def graph_proposal(
    request: Request,
    estimation_id: str,
    settings: Settings = Depends(get_settings),
) -> GraphProposalResponse:
    """Draft (or re-draft) a commercial proposal from the validated estimate.

    Stateless vs the graph: reads the checkpointer snapshot and runs the proposal
    LLM directly — does not re-run or mutate the graph.
    """
    request_id = get_request_id(request)
    if not settings.graph_proposal_enabled:
        raise HTTPException(
            status_code=503,
            detail="Proposal drafting is disabled (GRAPH_PROPOSAL_ENABLED=false).",
        )
    graph = _require_graph(request, request_id)
    config = {"configurable": {"thread_id": estimation_id}}
    snapshot = await graph.aget_state(config)
    estimate = (snapshot.values or {}).get("estimate")
    if not estimate:
        raise HTTPException(
            status_code=409,
            detail=(
                "No validated estimate for this estimation_id "
                "(run not far enough / unknown)."
            ),
        )
    try:
        logger.info(
            "graph_proposal",
            extra={"request_id": request_id, "estimation_id": estimation_id},
        )
        persona = persona_for(
            "proposal_agent",
            enabled=settings.graph_personas_enabled,
        )
        proposal = await build_proposal(
            estimate,
            (snapshot.values or {}).get("analysis_report") or {},
            persona=persona,
        )
    except Exception as exc:  # noqa: BLE001 — any LLM failure → 502
        logger.error(
            "graph_proposal_failed",
            extra={
                "request_id": request_id,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to draft the proposal.",
        ) from exc

    return GraphProposalResponse(
        estimation_id=estimation_id,
        title=proposal.title,
        executive_summary=proposal.executive_summary,
        scope=proposal.scope,
        total_engineer_days=proposal.total_engineer_days,
        body_markdown=proposal.body_markdown,
    )
