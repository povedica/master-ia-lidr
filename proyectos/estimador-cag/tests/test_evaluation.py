"""Parity tests for ``evaluate_estimation_structure`` (aligned with ai-engineering/estimator)."""

from app.services.evaluation import evaluate_estimation_structure

_WELL_FORMED = """\
## Inventory Management Web Platform

### Task Breakdown

| Task | Hours | Cost (EUR) |
|------|------:|------------|
| Requirements analysis and technical design | 16 | 1,000 |
| Database schema design and migrations | 12 | 750 |
| Authentication and role-based access control | 20 | 1,250 |
| Product and stock CRUD API | 24 | 1,500 |
| Automated reorder alert engine | 16 | 1,000 |
| CSV/Excel import and export module | 14 | 875 |
| Dashboard with key metrics and charts | 20 | 1,250 |
| Frontend: inventory views and search/filter | 24 | 1,500 |
| Frontend: admin panel and user management | 12 | 750 |
| AWS PostgreSQL integration and deployment | 10 | 625 |
| Testing (unit, integration, E2E) | 20 | 1,250 |
| Code review, QA, and bug fixing | 12 | 750 |

### Totals

- **Total hours:** 200
- **Total cost:** 12,500 EUR

### Recommended Team

- 1 Senior Backend Developer (lead)
- 1 Mid-level Full-Stack Developer
- 1 QA Engineer (part-time, last 3 weeks)

### Estimated Duration

**10 weeks** with a two-person development team.
"""


def test_well_formed_estimation_passes_all_checks() -> None:
    result = evaluate_estimation_structure(_WELL_FORMED, finish_reason="stop")
    assert result.has_title
    assert result.has_breakdown_table
    assert result.has_totals_section
    assert result.has_team_section
    assert result.has_duration_section
    assert result.declared_total_hours == 200
    assert result.sum_row_hours == 200
    assert result.hours_match is True
    assert result.declared_total_cost == 12500
    assert result.sum_row_cost == 12500
    assert result.cost_match is True
    assert result.finish_reason_ok is True
    assert result.score == 1.0
    assert result.issues == []


def test_end_turn_finish_reason_ok() -> None:
    result = evaluate_estimation_structure(_WELL_FORMED, finish_reason="end_turn")
    assert result.finish_reason_ok is True
    assert result.score == 1.0


def test_mismatched_total_hours_is_flagged() -> None:
    text = _WELL_FORMED.replace("**Total hours:** 200", "**Total hours:** 999")
    result = evaluate_estimation_structure(text, finish_reason="stop")
    assert result.hours_match is False
    assert any("Total hours mismatch" in msg for msg in result.issues)
    assert result.score < 1.0


def test_missing_table_is_detected() -> None:
    text = "## Just a title\n\nNo table here, just prose."
    result = evaluate_estimation_structure(text, finish_reason="stop")
    assert result.has_title is True
    assert result.has_breakdown_table is False
    assert any("breakdown table" in msg for msg in result.issues)
    assert result.sum_row_hours is None


def test_finish_reason_length_fails_check() -> None:
    result = evaluate_estimation_structure(_WELL_FORMED, finish_reason="length")
    assert result.finish_reason_ok is False
    assert any("truncated" in msg.lower() or "finish_reason" in msg for msg in result.issues)
    assert result.score < 1.0


def test_empty_text_scores_low() -> None:
    result = evaluate_estimation_structure("", finish_reason="stop")
    assert result.score < 0.5
    assert result.has_title is False
    assert result.has_breakdown_table is False
