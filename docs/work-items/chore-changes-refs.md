# Chore: Repository workflow and maintenance changes

## Objective

Track repository workflow, Cursor command, rules, and maintenance commits that do not belong to a specific feature work item.

## Scope

### Includes

- Cursor command updates.
- Cursor rule updates.
- Repository workflow documentation.
- General maintenance changes without a dedicated feature document.

### Excludes

- Feature implementation commits with a canonical `docs/work-items/feature-NNN-<slug>.md`.
- Bug fixes, improvements, specs, experiments, or ADRs that have their own canonical work item.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `9021c8f` | `docs(cursor): add start-front-task and write-front-feature commands` | Front-end feature workflow: `front-feature-NNN` naming, WIP draft PR policy, Vitest-first baby steps, and documentation gate. |
| `36d1378` | `docs(cursor): align feature start workflow` | Aligns Cursor workflow commands and spec rules around repository work items, strict feature start gates, WIP draft PRs, and the chore fallback commit log. |
| `67423f3` | `docs(work-item): add feature-016 Jinja2 prompt templates v2 spec` | Adds canonical feature work item for unified Jinja2 prompt templates (estimation v2 bundle) before implementation. |
| `3a0cb01` | `chore(cursor): add senior engineer persona to quality and start-task commands` | Shared opening line for consistent agent behavior on review and feature start. |
| `dd75315` | `chore(cursor): enforce spec-only discipline in write-feature command` | Clarifies write-feature must not implement; ambiguous prompts and completion checklist. |
