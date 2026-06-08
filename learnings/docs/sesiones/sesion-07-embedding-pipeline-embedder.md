# Sesión 07 — Embedding pipeline (incremento 3: OpenAI embedder)

## Enlaces

- [Feature 032: OpenAI embedder](../../docs/work-items/feature-032-embedding-pipeline-openai-embedder.md)
- Incremento anterior: [sesion-07-embedding-pipeline-chunker.md](sesion-07-embedding-pipeline-chunker.md)
- Siguiente: feature-033 (endpoint ingest)

## Decisión: API async

El ejercicio pide firmas síncronas, pero el repo es async de punta a punta (`AsyncOpenAI`, rutas FastAPI). Un cliente síncrono bloquearía el event loop bajo concurrencia. El embedder expone `async def embed_one` / `embed_many`; el CLI (034) usará `asyncio.run`.

## Batching y retry

- `embed_many` agrupa chunks en lotes de `EMBEDDING_PIPELINE_BATCH_SIZE` (default 100): **una** llamada `embeddings.create` por lote, no una por chunk.
- `RateLimitError`: hasta 3 intentos con backoff `1s → 2s → 4s` (`asyncio.sleep`). Otros errores se propagan sin reintento.
- Dimensión fija 1536 (default del modelo); no se pasa `dimensions` al API.

## Coste indicativo

`last_cost_usd = last_total_tokens / 1_000_000 * 0.02` (constante `COST_PER_MILLION_TOKENS`). Es estimación, no facturación real. Feature 033 leerá estos atributos para `IngestStats`.

## Logging

Un log INFO por lote: `embedding_batch_completed` con `batch_index`, `batch_size`, `batch_tokens`, `latency_ms` en `extra`.

## Aislamiento

No importar `app/services/semantic_cache/*`. Tests mockean `AsyncOpenAI`; el patrón fake del semantic cache no se reutiliza aquí (vectores de 1536 dims).

## Verificación

```bash
uv run pytest tests/embedding_pipeline/test_embedder.py
```
