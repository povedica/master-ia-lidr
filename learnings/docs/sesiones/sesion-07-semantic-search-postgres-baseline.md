# Sesión 07 — Postgres pgvector baseline (feature-036)

## Qué se añadió

- Servicio `postgres` en Docker Compose (`pgvector/pgvector:pg16`).
- `DATABASE_URL` en settings (async SQLAlchemy + asyncpg).
- Modelos ORM `documents` y `chunks` con `Vector(1536)` para `text-embedding-3-small`.
- Migración Alembic `0001_initial_schema.py` con extensión `vector`.

## Decisiones de esquema

- **Dos tablas**: trazabilidad a nivel documento y `ON DELETE CASCADE` en chunks.
- **`metadata` JSONB** en ambas tablas + índice GIN en `chunks.metadata` para consultas futuras por metadatos.
- **`source_path` único** en `documents` para detectar duplicados en el ingest persistente (feature-037).
- **Sin índice vectorial** (HNSW/IVFFlat): baseline con sequential scan antes de optimizar búsqueda.

## Comandos útiles

```bash
docker compose up -d postgres
docker compose exec postgres psql -U estimator -d estimator -c "SELECT version();"
export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
uv run alembic upgrade head
```

## Siguiente paso

Feature-037: persistir el ingest transaccionalmente sobre este esquema.
