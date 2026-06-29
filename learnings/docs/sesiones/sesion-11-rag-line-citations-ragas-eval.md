# Sesión 11 — RAG line citations y baseline RAGAS

**Feature:** [feature-052](../../docs/work-items/feature-052-rag-line-citations-ragas-eval.md)

## Qué se entregó

- Endpoint aditivo `POST /api/v1/estimate/rag` con schema `RagEstimationResult` (`schema_version=rag-1`).
- Citas por línea (`SourceReference`) y auditoría post-generación (`verify_citations`: `grounded_ok`, `dangling_citation`, `insufficient_data`).
- Re-fetch de contenido por `chunk_id` (`ChunkContentRepository`) sin ampliar el contrato de retrieval feature-050.
- Harness offline RAGAS: `evaluation/generation/golden_set.json` + `app/scripts/ragas_generation_eval.py`.

## Decisiones clave

- **chunk_id int** end-to-end (PostgreSQL `chunks.id`), no UUID del enunciado.
- **Instructor** vía `complete_structured`; no fork del Responses API.
- **Superficie separada** para no acoplar semantic cache / ACB / guardrails v2.
- Verificación literal de `evidence` como substring → Phase 2 (solo membership de `chunk_id` en Phase 1).

## Baseline RAGAS

No ejecutado en esta sesión: `DATABASE_URL` no estaba configurado en el entorno de verificación del agente.

Para reproducir localmente:

```bash
DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator \
OPENAI_API_KEY=... \
uv run python app/scripts/ragas_generation_eval.py
```

Interpretar `comparison.md` (5 filas + mean) y `quality_note.md` tras el run.

## Verificación automatizada

```bash
uv run pytest tests/test_rag_estimation_schema.py tests/test_citation_verification.py \
  tests/test_rag_estimation_endpoint.py tests/test_rag_estimation_service.py \
  tests/embedding_pipeline/test_generation_golden_set.py \
  tests/embedding_pipeline/test_generation_eval.py -q
```

Suite fast completa: ver work item feature-052 §Verification.
