# requirement-write

## Purpose
Create or refine one canonical requirement document before implementation.

## When to Use
- New feature, API endpoint, service, workflow, or setup task.
- A user idea exists but is not yet implementation-ready.
- A bug, experiment, or case needs a documented source of truth.

## Default Destinations
- Project work item: `learnings/second-brain-master-ia/proyectos/<project>/work-items/`
- Session-scoped work: `learnings/second-brain-master-ia/proyectos/<project>/sesiones/`

## Document Types (filename prefix)
- `feature-` user-facing capability, endpoint, or service behavior.
- `bugfix-` defect fix with reproduction and root cause.
- `spec-` cross-cutting contract, convention, or process.
- `exp-` hypothesis-driven experiment with success metric.
- `adr-` architectural decision (context, alternatives, decision, consequences).

If unsure, default to `feature-`.

## Workflow
1. Read the relevant repo rules for the task (see `.cursor/rules/11-spec-system.mdc`).
2. Gather context from code, docs, and Second Brain.
3. Pick the document type and prefix.
4. Write one canonical document with the sections required for that type:
   - feature: objective, scope, acceptance, verification, docs impact
   - bugfix: problem, expected, reproduction, root cause, fix, regression
   - spec: objective, contract, scope, rules, implications
   - exp: hypothesis, method, metric, effort cap, result
   - adr: context, options, decision, consequences
5. Keep the document implementation-oriented and small enough to execute.

## Rules
- One canonical document only.
- Do not block on missing detail if intent is obvious; flag the risk and propose a default.
- Never include real secrets.
- Prefer baby steps over broad architecture.
- Use English for technical documents in the repo; Spanish is acceptable only for reflective Second Brain notes when appropriate.

## Related
- `write-feature`
- `requirement-validate`
- `requirement-design`
- `requirement-tasks`
