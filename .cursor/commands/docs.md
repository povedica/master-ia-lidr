# docs

## Purpose
Keep project documentation synchronized across canonical repository work items and supporting Second Brain notes.

## When to Use
Use after setup changes, architecture decisions, FastAPI changes, LLM integration changes, or session work.

## Documentation Targets
- Canonical work items: `docs/work-items/feature-NNN-<slug>.md`
- Session work mirror: `learnings/docs/sesiones/`
- Reusable learnings mirror: `learnings/aprendizajes/`
- Retrospectives mirror: `learnings/retrospectiva/`
- Runtime/setup docs: project `README.md`

## Rules
- Write learning notes in Spanish.
- Keep technical names, commands, paths, and code symbols in English.
- Avoid duplicating the same content across many notes.
- Promote only reusable knowledge to `aprendizajes/`.
- Never document real API keys or secrets.

## Output
Report:
- files updated
- what was documented
- what was intentionally not documented
