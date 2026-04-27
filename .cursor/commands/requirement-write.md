# requirement-write

## Purpose
Create or refine one canonical requirement document before implementation.

## When to Use
- New feature, API endpoint, service, workflow, or setup task.
- A user idea exists but is not yet implementation-ready.
- A bug, experiment, or case needs a documented source of truth.

## Default Destinations
- Project feature/decision: `second-brain-master-ia/proyectos/<project>/decisiones/`
- Session-scoped work: `second-brain-master-ia/proyectos/<project>/sesiones/`

## Workflow
1. Read the relevant repo rules for the task.
2. Gather context from code, docs, and Second Brain.
3. Detect the work type:
   - `feature`
   - `bug`
   - `hotfix`
   - `experiment`
   - `case`
4. Write one canonical document with:
   - objective
   - context
   - bounded scope
   - acceptance criteria
   - verification plan
   - documentation impact
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
