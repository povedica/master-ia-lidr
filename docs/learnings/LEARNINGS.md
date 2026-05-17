# Project learnings log

Append-only entries. Format: see `.cursor/skills/learnings/SKILL.md`.

---

## [LRN-20260517-001] best_practice

**Registrado:** 2026-05-17  
**Prioridad:** medium  
**Estado:** pending  
**Área:** docs

### Resumen

When using `/start-task`, baby-step commits need an explicit user instruction; default Cursor user rules forbid unprompted commits.

### Detalle

`start-task` Phase 5 recommends one commit per plan step. User rules (`committing-changes-with-git`) require commits only when the user asks. Agents should treat `start-task` as "commit each step only if the user says so" or update `start-task.md` to request commits at kickoff.

### Acción sugerida

Clarify `.cursor/commands/start-task.md` (e.g. "On `/start-task`, user opts in to per-step commits") or ask once at task start: "¿Commits por paso?".

### Metadata

- Origen: conversación (feature-014 Langfuse)
- Archivos: `.cursor/commands/start-task.md`
- Ver también: feature-014 implementation decisions

---
