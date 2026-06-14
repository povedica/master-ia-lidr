# Sesión 07 — Índice HNSW pgvector (feature-040)

## Contexto

Tras el baseline de sequential scan (features 036–038), una pasada de observabilidad (2026-06-14) confirmó:

| Métrica | Antes | Después (feature-040) |
|---------|-------|------------------------|
| Tabla / columna | `chunks.embedding` vector(1536) | Igual |
| Chunks / vectores | 39 / 39 | 39 / 39 |
| Índices HNSW | 0 | 1 (`ix_chunks_embedding_hnsw`) |
| Tamaño índice | — | ~312 kB |
| Tamaño tabla total | ~504 kB | ~816 kB |

## Qué se añadió

- Migración Alembic `0002_add_chunks_embedding_hnsw_index.py`.
- Índice `ix_chunks_embedding_hnsw` con `vector_cosine_ops`, `m=16`, `ef_construction=64`, predicado `WHERE embedding IS NOT NULL`.
- Script `scripts/pgvector_observability.sql` para métricas de dashboard.
- Documentación técnica actualizada (README, `docs/technical` §24, arquitectura HTML, ADR-001).

## Alineación operador ↔ métrica

- Búsqueda: `cosine_distance` → operador `<=>`.
- Índice: `vector_cosine_ops` (no L2 ni inner product).
- Sin cambios en `POST /api/v1/search`.

## EXPLAIN (diagnóstico)

Con ~39 filas el planner puede elegir sequential scan en condiciones normales. Con `SET enable_seqscan = off` (solo diagnóstico):

```text
Index Scan using ix_chunks_embedding_hnsw on chunks
  Order By: (embedding <=> $0)
```

## Comandos

```bash
export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
uv run alembic upgrade head
docker compose exec -T postgres psql -U estimator -d estimator < scripts/pgvector_observability.sql
uv run pytest tests/test_alembic_migration.py -q
```

## Alertas resueltas

- ~~No hay índice HNSW sobre embeddings~~ → `ix_chunks_embedding_hnsw` creado.
- `idx_scan` en índice vectorial: verificar tras tráfico de búsqueda real (script de observabilidad).

## Referencias

- Work item: `docs/work-items/feature-040-chunks-hnsw-vector-index.md`
- Technical doc: `docs/technical/README.md` §24
