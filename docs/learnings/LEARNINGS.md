# Project learnings log

Append-only entries. Format: see `.cursor/skills/learnings/SKILL.md`.

---

## [LRN-20260609-001] best_practice

**Registrado:** 2026-06-09  
**Prioridad:** high  
**Estado:** pending  
**Área:** api

### Resumen

Semantic vector search is not keyword search: interpret `distance` and metadata together; duplicate ingests can flood top-k.

### Detalle

During feature-038 manual verification, query `REST API with SAML authentication for public educational sector` ranked OAuth fintech chunks #1–2 (distance ~0.65) while the best education-sector match (Course catalog API) was #3 — same distance, different sector. The corpus had no SAML text. Duplicate ingests of `BUD-2024-014` occupied two slots with identical distance. Stronger matches (OAuth+fintech query) showed distance ~0.42.

Correct operator reading: pgvector cosine distance `<=>` — lower is better; 0.65+ on a small corpus often means moderate similarity, not a confident hit.

### Acción sugerida

Document query examples in feature-038 work item and feature-039 script; enforce unique `source_path` at ingest; consider metadata filters or hybrid search for production.

### Metadata

- Origen: conversación (feature-038 manual search analysis)
- Archivos: `docs/work-items/feature-038-semantic-search-endpoint-pgvector.md`, `app/embedding_pipeline/search_repository.py`
- Ver también: feature-039

---

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
