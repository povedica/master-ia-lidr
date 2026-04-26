# start-task

## Purpose
Start a task with enough context, a small plan, and clear verification.

## When to Use
Use when starting any feature, bug fix, refactor, experiment, or documentation task.

## Workflow
1. Identify task type: feature, bug, refactor, docs, or experiment.
2. Read relevant `.cursor/rules/`.
3. Inspect existing code and tests before editing.
4. Define scope and exclusions.
5. Propose the smallest useful implementation plan.
6. Identify documentation target in `second-brain-master-ia/proyectos/estimador-cag/`.

## Output
Return:
- task summary
- relevant files
- proposed baby steps
- test or verification plan
- documentation destination

## Rules
- Do not code before context is gathered.
- Do not create large plans for small tasks.
- Ask only when a decision blocks progress.
- Do not create or commit real `.env` secrets.
