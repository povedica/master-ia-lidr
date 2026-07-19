"""The hand-written agent loop (Session 12 + Session 13 two-phase APIs).

DELIBERATE EXCEPTION: this module uses the raw OpenAI Responses API directly —
not LiteLLM/Instructor — so each reasoning item, function call, and output is visible.

* ``run_estimation_agent`` — Session 12 pedagogical single-shot loop (kept for
  CLI/HTTP backward compatibility).
* ``run_structure_agent`` / ``run_task_hours_recovery_agent`` — Session 13
  two-phase APIs reused by the LangGraph estimation graph (feature-066).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.agentic.agent_schemas import (
    AgentEstimate,
    AgentRunResult,
    AgentStep,
    AgentStructure,
    AgentTaskDerivation,
    AgentTaskHoursRun,
    AgentTaskRef,
    AgentTrace,
)
from app.services.agentic.agent_tools import (
    HOURS_TOOL_SCHEMAS,
    TOOL_SCHEMAS,
    ConsensusFn,
    RetrievalBackend,
    dispatch_tool,
)

logger = logging.getLogger(__name__)

STRUCTURE_SYSTEM_PROMPT = """\
You are a senior software-delivery architect acting as an estimation agent. You \
receive a structured project brief and must DECOMPOSE it into the functional \
MODULES and the concrete engineering TASKS needed to deliver it.

This is a STRUCTURE-ONLY step: you do NOT estimate hours and you have NO \
historical sources — rely on your engineering judgement about what the project \
entails. The hours are derived in a later step by searching a historical corpus \
per task, so a good, granular decomposition here is what matters.

- Organise the work into functional blocks (e.g. Authentication & Access, \
Payments & Billing, Core Domain, Data & Integrations, Frontend/UX, Infrastructure \
& DevOps, Security & Compliance, QA & Testing, Project Management). Use the \
modules that fit THIS project; add sector-specific ones when the brief calls for \
them; omit the ones that do not apply.
- Within each module, break the work into granular tasks with a short \
`description`. Be thorough — typically 5-9 modules with several tasks each — so a \
delivery team could plan from it.
- Set `confidence` from how well-specified the brief is, and explain your \
decomposition in `reasoning`. If the brief is too vague to scope responsibly, \
return an empty `modules` list and say so in `reasoning`.\
"""

HOURS_RECOVERY_SYSTEM_PROMPT = """\
You are an estimation agent recovering hours for tasks that the standard per-task \
search could NOT ground. Each task below came back with no usable historical \
analog (or a low-confidence / contradictory one). Your job is to try harder.

Method — for EACH task in the list:
1. Call `search_budgets` with a focused, task-specific query. If the first search \
finds nothing usable, REFORMULATE — reword it, use synonyms, describe the \
underlying capability instead of the product name, or relax/drop the sector \
filter — and search again. You decide how many attempts a task is worth.
2. When you have historical analogs, call `derive_task_hours` with the task and \
those neighbours (pass each neighbour's estimated_hours AND its distance exactly \
as search_budgets returned them). This computes the hours deterministically.
3. If after genuine effort you still find no analog, leave that task unresolved — \
do NOT invent hours. Move on to the next task.

When you have processed every task, call `validate_estimate` once over the tasks \
you managed to ground, address anything it flags, then stop calling tools.

You have exactly these tools: `search_budgets`, `derive_task_hours`, \
`validate_estimate`. Never invent hours: they must come from `derive_task_hours`.\
"""

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


async def run_structure_agent(
    brief: str,
    *,
    client: Any,
    model: str,
    reasoning_effort: str = "medium",
    persona: str | None = None,
) -> tuple[AgentStructure, AgentTrace]:
    """Phase 1 — propose module→task structure (no tools, no hours)."""
    instructions = STRUCTURE_SYSTEM_PROMPT
    if persona and persona.strip():
        instructions = (
            f"{STRUCTURE_SYSTEM_PROMPT}\n\n# Additional operator instructions\n{persona.strip()}"
        )

    logger.info(
        "agent_structure_start",
        extra={"model": model, "effort": reasoning_effort, "persona": bool(persona)},
    )
    response = await client.responses.parse(
        model=model,
        instructions=instructions,
        input=[{"role": "user", "content": brief}],
        reasoning={"effort": reasoning_effort, "summary": "auto"},
        text_format=AgentStructure,
        store=True,
    )
    structure: AgentStructure = response.output_parsed
    reasoning_summary = _extract_reasoning_summary(getattr(response, "output", []) or [])

    task_count = sum(len(module.tasks) for module in structure.modules)
    trace = AgentTrace(
        steps=[
            AgentStep(
                step=1,
                reasoning_summary=reasoning_summary,
                tool="propose_structure",
                tool_args={"modules": len(structure.modules), "tasks": task_count},
                observation=(
                    f"decomposed into {len(structure.modules)} modules / {task_count} tasks "
                    f"(confidence={structure.confidence})"
                ),
            )
        ]
    )
    logger.info(
        "agent_structure_done",
        extra={
            "modules": len(structure.modules),
            "tasks": task_count,
            "confidence": structure.confidence,
        },
    )
    return structure, trace


async def run_task_hours_recovery_agent(
    flagged_tasks: list[AgentTaskRef],
    *,
    client: Any,
    model: str,
    reasoning_effort: str = "medium",
    max_iterations: int = 10,
    retrieval_backend: RetrievalBackend,
    consensus_fn: ConsensusFn,
    persona: str | None = None,
) -> AgentTaskHoursRun:
    """Phase 2 — reason→act→observe loop over flagged tasks only."""
    if not flagged_tasks:
        return AgentTaskHoursRun(derivations=[], trace=AgentTrace(), iterations=0)

    instructions = HOURS_RECOVERY_SYSTEM_PROMPT
    if persona and persona.strip():
        instructions = (
            f"{HOURS_RECOVERY_SYSTEM_PROMPT}\n\n# Additional operator instructions\n"
            f"{persona.strip()}"
        )

    task_lines = "\n".join(
        f"- module={task.module!r} task={task.task!r}"
        + (f" description={task.description!r}" if task.description else "")
        + f" (flagged: {task.reason})"
        for task in flagged_tasks
    )
    user_message = (
        "Recover hours for these tasks. For each, search historical analogs "
        "(reformulating as needed) and derive its hours; leave it unresolved if no "
        f"analog exists.\n\n{task_lines}"
    )

    trace = AgentTrace()
    derivations: dict[tuple[str, str], AgentTaskDerivation] = {}
    step_no = 0
    stopped_reason: str = "completed"

    logger.info(
        "agent_hours_recovery_start",
        extra={
            "model": model,
            "effort": reasoning_effort,
            "flagged": len(flagged_tasks),
            "persona": bool(persona),
        },
    )
    response = await client.responses.create(
        model=model,
        instructions=instructions,
        input=[{"role": "user", "content": user_message}],
        tools=HOURS_TOOL_SCHEMAS,
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
                    result = await dispatch_tool(
                        name,
                        raw_args,
                        backend=retrieval_backend,
                        consensus_fn=consensus_fn,
                    )
                except Exception as exc:  # noqa: BLE001 — return error so the model self-corrects
                    logger.warning(
                        "agent_tool_error",
                        extra={"tool": name, "error": str(exc)[:200]},
                    )
                    result = {"error": f"{type(exc).__name__}: {exc}"}

            if name == "derive_task_hours" and "error" not in result:
                key = (str(result.get("module", "")), str(result.get("task", "")))
                derivations[key] = AgentTaskDerivation(
                    module=key[0],
                    task=key[1],
                    estimated_hours=result.get("estimated_hours"),
                    reliability=result.get("reliability"),
                    has_match=bool(result.get("has_match", False)),
                )

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
            tools=HOURS_TOOL_SCHEMAS,
            reasoning={"effort": reasoning_effort, "summary": "auto"},
            store=True,
        )
        iterations += 1

    logger.info(
        "agent_hours_recovery_done",
        extra={
            "iterations": iterations,
            "steps": len(trace.steps),
            "derived": len(derivations),
            "stopped_reason": stopped_reason,
        },
    )
    return AgentTaskHoursRun(
        derivations=list(derivations.values()),
        trace=trace,
        iterations=iterations,
        stopped_reason=stopped_reason,  # type: ignore[arg-type]
    )


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
