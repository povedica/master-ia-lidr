# Sesión 07 — Embedding pipeline (incremento 4: ingest endpoint)

## Enlaces

- [Feature 033: ingest endpoint](../../docs/work-items/feature-033-embedding-pipeline-ingest-endpoint.md)
- Incrementos previos: feature-030 (schemas), feature-031 (chunker), feature-032 (embedder)
- Siguiente: feature-034 (CLI cosine)

## Objetivo del incremento

Exponer el pipeline por HTTP: `POST /api/v1/embeddings/ingest` orquesta chunking + embedding y devuelve `IngestResponse`.

## Decisiones vs ejercicio

| Ejercicio | Repo |
|-----------|------|
| Ruta `/embeddings/ingest` sin versión | `POST /api/v1/embeddings/ingest` (convención FastAPI del repo) |
| Router en paquete del pipeline | Router canónico en `app/routers/embeddings.py` |
| Stub `app/embedding_pipeline/router.py` | Se mantiene como nota; no se usa |

## Contrato HTTP

- Request: `IngestRequest` (`budgets: list[Budget]`)
- Response: `IngestResponse` (`chunks`, `stats`)
- Errores: `422` validación Pydantic; `500` mensaje genérico + log con `request_id` y `error_type`

## Verificación

```bash
uv run pytest tests/embedding_pipeline/test_router.py
uv run uvicorn app.main:app --reload  # Swagger en /docs
```
