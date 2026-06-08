# Sesión 07 — Embedding pipeline (incremento 2: chunker estructural)

## Enlaces

- [Feature 031: structural chunker](../../docs/work-items/feature-031-embedding-pipeline-structural-chunker.md)
- Incremento anterior: [sesion-07-embedding-pipeline-schemas.md](sesion-07-embedding-pipeline-schemas.md)
- Siguiente: feature-032 (embedder)

## Decisión: chunking estructural

Un componente de presupuesto = un chunk. No hay splitting recursivo, semántico ni por tamaño fijo en este incremento.

## Esquema de `chunk_id`

`{budget_id}::{component_id}` — doble dos puntos para separar presupuesto y componente sin ambigüedad (p. ej. `BUD-2024-014::AUTH-001`).

## Plantilla de texto

El contexto del presupuesto padre va embebido en el `text` del chunk (cabecera con proyecto, sector, año y tecnología principal), seguido de las cinco líneas del componente. La plantilla debe permanecer estable byte a byte: el sanity check de embeddings (feature-034) depende de formato consistente.

## Token counting

Un solo encoder `tiktoken.encoding_for_model("text-embedding-3-small")` por instancia de `JSONStructuralChunker`; no recrear el encoder por componente.

## Logging

Un log INFO por llamada a `chunk()` con `extra={"total_budgets": n, "total_chunks": m}` (`chunker_completed`). Stdlib `logging`, no `structlog`.

## Verificación

```bash
uv run pytest tests/embedding_pipeline/test_chunker.py
```
