"""Pure helpers shared by the multi-agent nodes.

Kept free of I/O so they are unit-testable and reusable by the fan-out branch,
the recovery join, and the estimate builder.
"""

from __future__ import annotations

# References are historical engineer-HOURS; the headline estimate is engineer-DAYS.
HOURS_PER_DAY = 8.0

# Grounded task below this reliability is doubtful enough for recovery.
LOW_RELIABILITY = 0.35


def modules_from_structure(structure: dict | None) -> list[dict]:
    """``AgentStructure`` dump → module→task list for the fan-out / gate 1."""
    modules: list[dict] = []
    for module in (structure or {}).get("modules") or []:
        modules.append(
            {
                "name": module.get("name"),
                "tasks": [
                    {"name": task.get("name"), "description": task.get("description")}
                    for task in (module.get("tasks") or [])
                    if task.get("name")
                ],
            }
        )
    return modules


def flag_reason(task_hours: dict) -> str | None:
    """Why (if at all) a per-task hours row is worth agentic recovery.

    Uses ``hour_range`` (master-ia) and accepts legacy ``hours_range``.
    """
    if not task_hours.get("has_match"):
        return "no historical analog under the distance threshold"
    if task_hours.get("hour_range") is not None or task_hours.get("hours_range") is not None:
        return "historical analogs contradict (a range, not a point)"
    reliability = task_hours.get("reliability")
    if reliability is not None and reliability < LOW_RELIABILITY:
        return f"low reliability ({reliability})"
    return None


def recompute_estimate_totals(modules: list[dict]) -> dict:
    """Headline totals derived from a module→task tree's ``estimated_hours``."""
    total_hours = 0.0
    grounded = 0
    total_tasks = 0
    for module in modules or []:
        for task in module.get("tasks") or []:
            total_tasks += 1
            hours = task.get("estimated_hours")
            if hours is not None:
                total_hours += hours
                grounded += 1

    ratio = round(grounded / total_tasks, 3) if total_tasks else 0.0
    if total_tasks and grounded == total_tasks:
        confidence = "high"
    elif grounded == 0:
        confidence = "low"
    else:
        confidence = "medium"
    return {
        "total_engineer_hours": round(total_hours, 1),
        "total_engineer_days": round(total_hours / HOURS_PER_DAY),
        "grounded_task_ratio": ratio,
        "confidence": confidence,
    }


def build_estimate(approved_modules: list[dict], task_hours: list[dict]) -> dict:
    """Assemble the structured estimate from the approved tree + per-task hours."""
    by_key = {(row.get("module"), row.get("task")): row for row in task_hours}
    out_modules: list[dict] = []
    for module in approved_modules:
        tasks_out: list[dict] = []
        for task in module.get("tasks") or []:
            est = by_key.get((module.get("name"), task.get("name")))
            tasks_out.append(
                {
                    "name": task.get("name"),
                    "description": task.get("description"),
                    "estimated_hours": est.get("estimated_hours") if est else None,
                    "reliability": est.get("reliability") if est else None,
                    "has_match": bool(est and est.get("has_match")),
                }
            )
        out_modules.append({"name": module.get("name"), "tasks": tasks_out})

    return {"modules": out_modules, **recompute_estimate_totals(out_modules)}
