# Sesión 11 — RAG line citations y baseline RAGAS

**Feature:** [feature-052](../../docs/work-items/feature-052-rag-line-citations-ragas-eval.md)

## Qué se entregó

- Endpoint aditivo `POST /api/v1/estimate/rag` con schema `RagEstimationResult` (`schema_version=rag-1`).
- Citas por línea (`SourceReference`) y auditoría post-generación (`verify_citations`: `grounded_ok`, `dangling_citation`, `insufficient_data`).
- Re-fetch de contenido por `chunk_id` (`ChunkContentRepository`) sin ampliar el contrato de retrieval feature-050.
- Harness offline RAGAS: `evaluation/generation/golden_set.json` + `app/scripts/ragas_generation_eval.py`.
- **UI (`web/`):** botón **Run RAG estimate**, tabla de citas (`RagCitationTable`) y resumen de auditoría (`RagCitationSummary`) en `EstimateResultPanel`.
- **FR-17:** `format_ragas_answer()` (prosa para RAGAS) y métricas NaN-safe (`null` en JSON, `n/a` en markdown).

## Decisiones clave

- **chunk_id int** end-to-end (PostgreSQL `chunks.id`), no UUID del enunciado.
- **Instructor** vía `complete_structured`; no fork del Responses API.
- **Superficie separada** para no acoplar semantic cache / ACB / guardrails v2.
- Verificación literal de `evidence` como substring → Phase 2 (solo membership de `chunk_id` en Phase 1).

## Baseline RAGAS

Run histórico (pre-FR-17): `evaluation/generation/results/20260629T185540Z/`.

| Métrica | Media | Notas |
| --- | ---: | --- |
| faithfulness | 0.569 | Aceptable; peor q4-payments-mobile (0.385). |
| answer_relevancy | **NaN** | Run anterior usaba JSON crudo; corregido con `format_ragas_answer()`. |
| context_precision | 0.863 | Retrieval bien rankeado. |
| context_recall | 0.140 | Métrica más débil; q1–q3 en 0.0. Revisar `ground_truth` y cobertura retrieval. |

Tras FR-17, re-ejecutar localmente para baseline corregido:

```bash
DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator \
OPENAI_API_KEY=... \
uv run python app/scripts/ragas_generation_eval.py
```

Interpretar `comparison.md` (5 filas + mean, `n/a` si alguna métrica no es finita) y `quality_note.md`.

## Verificación automatizada

```bash
# Backend feature-052
uv run pytest tests/test_rag_estimation_schema.py tests/test_citation_verification.py \
  tests/test_rag_estimation_endpoint.py tests/test_rag_estimation_service.py \
  tests/embedding_pipeline/test_generation_golden_set.py \
  tests/embedding_pipeline/test_generation_eval.py -q

# Frontend citas RAG
cd web && npm test
```

## Manual (opcional)

1. `POST /api/v1/estimate/rag` con corpus poblado; revisar `citation_summary` y `sources[]`.
2. En `web/`, rellenar transcript → **Run RAG estimate** → pestaña **RAG citations**.
