# Sesión 07 — Embedding pipeline (incremento 1: schemas)

## Enlaces

- [Feature 030: scaffold + schemas](../../docs/work-items/feature-030-embedding-pipeline-scaffold-schemas.md)
- Incrementos siguientes: feature-031 (chunker), feature-032 (embedder), feature-033 (ingest endpoint), feature-034 (CLI cosine)

## Objetivo del incremento

Crear el módulo aislado `app/embedding_pipeline/` y los modelos Pydantic v2 que definen el contrato de ingestión (presupuestos → chunks → embeddings). Sin chunking, sin llamadas OpenAI, sin rutas HTTP en este paso.

## Contrato de schemas

| Modelo | Rol |
|--------|-----|
| `ClientMetadata`, `BudgetComponent`, `Budget` | Entrada JSON de presupuestos históricos |
| `Chunk` | Fragmento de texto + metadatos + `token_count` |
| `EmbeddedChunk` | Extiende `Chunk` con `embedding: list[float]` |
| `IngestStats` | Estadísticas tipadas (no `dict` suelto) |
| `IngestRequest` / `IngestResponse` | Contrato HTTP futuro (feature-033) |

Decisión: `IngestStats` como modelo explícito para alinear con convenciones del repo (`app/schemas/*`) manteniendo las claves JSON requeridas por el ejercicio.

## Aislamiento

El pipeline de embeddings es un módulo de aprendizaje separado. No importa ni modifica `app/services/semantic_cache/*`.

## Verificación

```bash
uv run pytest tests/embedding_pipeline/test_schemas.py
uv run python -c "from app.embedding_pipeline.schemas import Budget, Chunk, EmbeddedChunk, IngestRequest, IngestResponse"
```

## PR

- WIP: https://github.com/povedica/master-ia-lidr/pull/25
