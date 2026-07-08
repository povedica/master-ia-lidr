"""The hand-written agent loop (Session 12).

DELIBERATE EXCEPTION: this module uses the raw OpenAI Responses API directly —
not LiteLLM/Instructor — so each reasoning item, function call, and output is visible.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.agentic.agent_schemas import (
    AgentEstimate,
    AgentRunResult,
    AgentStep,
    AgentTrace,
)
from app.services.agentic.agent_tools import TOOL_SCHEMAS, RetrievalBackend, dispatch_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an estimation agent for a software consultancy. You receive the raw \
transcript of a discovery meeting and must produce a grounded effort estimate in \
engineer-hours.

Method — follow it step by step:
1. Read the transcript and DECOMPOSE the project into its distinct components \
(for example: a business backend, an ERP integration, a mobile app, an analytics \
dashboard). Real projects usually have several.
2. For EACH component, call `search_budgets` with a focused, component-specific \
query to retrieve how much analogous work has cost historically, in engineer-hours. \
Do one search per component — do not try to cover the whole project in a single \
query.
3. Once you have reference hours for every component, call `calculate_estimate` \
with all the components and their reference amounts to get a partial-and-total \
breakdown.
4. Call `validate_estimate` as the LAST tool step and fix anything it flags \
(e.g. a component with no historical reference — search again for it).
5. When you are satisfied, stop calling tools. You will then be asked to return the \
final structured estimate.

You have exactly these tools: `search_budgets`, `calculate_estimate`, \
`validate_estimate`. Ground your numbers in what `search_budgets` returns; when you \
must assume something the transcript did not specify, record it as an assumption.\
"""

FINAL_INSTRUCTION = (
    "Return the final structured estimate now, consolidating the components you "
    "costed. Set total_hours to the sum of the components, list the assumptions you "
    "made, and choose a confidence level reflecting how well the historical budgets "
    "matched the requested work."
)


def _extract_reasoning_summary(output: list[Any]) -> str | None:
    parts: list[str] = []
    for item in output:
        if getattr(item, "type", None) != "reasoning":
            continue
        for summary in getattr(item, "summary", None) or []:
            text = getattr(summary, "text", None)
            if text:
                parts.append(text)
    return " ".join(parts) if parts else None


def _function_calls(output: list[Any]) -> list[Any]:
    return [item for item in output if getattr(item, "type", None) == "function_call"]


async def run_estimation_agent(
    transcript: str,
    *,
    client: Any,
    model: str,
    reasoning_effort: str = "medium",
    max_iterations: int = 10,
    retrieval_backend: RetrievalBackend,
) -> AgentRunResult:
    """Run the manual agent loop over a transcript and return estimate + trace."""
    trace = AgentTrace()
    step_no = 0
    stopped_reason: str = "completed"

    logger.info(
        "agent_run_start",
        extra={"model": model, "effort": reasoning_effort},
    )
    response = await client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=[{"role": "user", "content": transcript}],
        tools=TOOL_SCHEMAS,
        reasoning={"effort": reasoning_effort, "summary": "auto"},
        store=True,
    )
    iterations = 1

    while True:
        calls = _function_calls(response.output)
        if not calls:
            break
        if iterations >= max_iterations:
            stopped_reason = "max_iterations"
            logger.warning(
                "agent_max_iterations_reached",
                extra={"iterations": iterations},
            )
            break

        reasoning_summary = _extract_reasoning_summary(response.output)
        first_step_in_turn = step_no + 1
        tool_outputs: list[dict[str, Any]] = []
        for call in calls:
            step_no += 1
            step_reasoning = (
                reasoning_summary
                if step_no == first_step_in_turn
                else f"(parallel tool call in the same turn as STEP {first_step_in_turn})"
            )
            name = getattr(call, "name", "unknown")
            try:
                raw_args = json.loads(call.arguments)
            except (json.JSONDecodeError, TypeError) as exc:
                raw_args = {}
                result: dict[str, Any] = {"error": f"arguments were not valid JSON: {exc}"}
            else:
                try:
                    result = await dispatch_tool(name, raw_args, backend=retrieval_backend)
                except Exception as exc:  # noqa: BLE001 — return error so the model self-corrects
                    logger.warning(
                        "agent_tool_error",
                        extra={"tool": name, "error": str(exc)[:200]},
                    )
                    result = {"error": f"{type(exc).__name__}: {exc}"}

            observation = result.get("summary") or result.get("error") or json.dumps(result)[:200]
            trace.steps.append(
                AgentStep(
                    step=step_no,
                    reasoning_summary=step_reasoning,
                    tool=name,
                    tool_args=raw_args,
                    observation=observation,
                )
            )
            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                }
            )

        response = await client.responses.create(
            model=model,
            previous_response_id=response.id,
            input=tool_outputs,
            tools=TOOL_SCHEMAS,
            reasoning={"effort": reasoning_effort, "summary": "auto"},
            store=True,
        )
        iterations += 1

    estimate: AgentEstimate | None = None
    if stopped_reason != "max_iterations":
        try:
            parsed = await client.responses.parse(
                model=model,
                previous_response_id=response.id,
                input=[{"role": "user", "content": FINAL_INSTRUCTION}],
                text_format=AgentEstimate,
                store=True,
            )
            estimate = parsed.output_parsed
            iterations += 1
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "agent_final_parse_failed",
                extra={"error": str(exc)[:300]},
            )
            stopped_reason = "no_final_estimate"

    if estimate is None and stopped_reason == "completed":
        stopped_reason = "no_final_estimate"

    logger.info(
        "agent_run_done",
        extra={
            "iterations": iterations,
            "steps": len(trace.steps),
            "stopped_reason": stopped_reason,
            "total_hours": estimate.total_hours if estimate else None,
        },
    )
    return AgentRunResult(
        estimate=estimate,
        trace=trace,
        iterations=iterations,
        stopped_reason=stopped_reason,  # type: ignore[arg-type]
    )
