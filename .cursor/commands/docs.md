# docs

## Purpose
Synchronize project documentation with the repository and Second Brain.

## When to Use
Use after setup changes, architecture decisions, FastAPI changes, LLM integration changes, or session work.

## Documentation Targets
- Session work (vault): `learnings/second-brain-master-ia/proyectos/estimador-cag/sesiones/` — **versioned git mirror:** `learnings/docs/sesiones/`
- Work items (vault): `learnings/second-brain-master-ia/proyectos/estimador-cag/work-items/` — **versioned git mirror:** `docs/work-items/`
- Reusable learnings (vault): `learnings/second-brain-master-ia/proyectos/estimador-cag/aprendizajes/` — **versioned git mirror:** `learnings/aprendizajes/`
- Retrospectives (vault): `learnings/second-brain-master-ia/proyectos/estimador-cag/retrospectivas/` — **versioned git mirror:** `learnings/retrospectiva/`
- **After vault edits**, run `bash scripts/sync-estimador-cag-docs.sh` from the repo root before committing (updates `docs/`, `learnings/docs/sesiones/`, `learnings/aprendizajes/`, and `learnings/retrospectiva/`).
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
