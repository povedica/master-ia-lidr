"""Activity feed helpers for Session 13 stream mode — network-free."""

from __future__ import annotations

from app.services.estimation_graph.activity import GraphActivityLog, describe_node


def test_describe_classifier_reads_complexity() -> None:
    lines = describe_node("classifier_agent", {"complexity": "high"})
    assert lines == [
        {"node": "classifier", "label": "Classifier", "message": "Complejidad: high"}
    ]


def test_describe_structure_counts_modules_and_tasks() -> None:
    update = {"structure": {"modules": [{"tasks": [1, 2]}, {"tasks": [3]}]}}
    (line,) = describe_node("structure_agent", update)
    assert line["node"] == "structure"
    assert line["message"] == "2 módulos · 3 tareas"


def test_describe_hours_fanout_one_line_per_task() -> None:
    update = [
        {"task_hours": [{"task": "A", "has_match": True, "estimated_hours": 37}]},
        {"task_hours": [{"task": "B", "has_match": False, "estimated_hours": None}]},
    ]
    lines = describe_node("estimate_task_hours", update)
    assert [line["message"] for line in lines] == ["A: 37 h", "B: SIN ANÁLOGO"]
    assert all(line["node"] == "hours" for line in lines)


def test_describe_recover_reads_total_days() -> None:
    update = {"estimate": {"total_engineer_days": 292}, "task_hours": []}
    (line,) = describe_node("recover_and_handover", update)
    assert line["node"] == "recover"
    assert "292 jornadas" in line["message"]


def test_describe_analysis_reads_confidence_and_ratio() -> None:
    update = {
        "analysis_report": {
            "overall_confidence": "medium",
            "grounded_task_ratio": 0.59,
        }
    }
    (line,) = describe_node("analysis_agent", update)
    assert line["node"] == "analysis"
    assert "medium" in line["message"] and "59%" in line["message"]


def test_describe_interrupt_and_unknown_never_raise() -> None:
    assert describe_node("__interrupt__", None)[0]["message"].startswith("⏸")
    assert describe_node("mystery_node", {"weird": 1})[0]["node"] == "mystery_node"


def test_activity_log_in_process_fallback_appends_reads_and_resets() -> None:
    log = GraphActivityLog(redis_client=None)
    log.append("run-1", node="classifier", label="Classifier", message="Complejidad: high")
    log.append(
        "run-1",
        node="structure",
        label="Structure",
        message="11 módulos · 123 tareas",
    )
    entries = log.read("run-1")
    assert [e["seq"] for e in entries] == [0, 1]
    assert entries[1]["node"] == "structure"
    assert log.read("run-2") == []
    log.reset("run-1")
    assert log.read("run-1") == []
