# Sesión 07 — Semantic search endpoint (feature-038)

## Qué se añadió

- `POST /api/v1/search` — embed query + top-k chunks por distancia coseno en Postgres.
- Módulos: `app/routers/search.py`, `app/embedding_pipeline/search.py`, `search_repository.py`.
- Schemas: `SearchRequest`, `SearchResult`, `SearchResponse` en `schemas.py`.
- 20 tests deterministas (embedder y DB mockeados).

## Flujo

1. Cliente envía `query` + `k`.
2. `OpenAIEmbedder.embed_one(query)` — **una** llamada OpenAI por búsqueda.
3. SQL: `embedding <=> query_vector` (cosine distance), `WHERE embedding IS NOT NULL`, `ORDER BY distance`, `LIMIT k`.
4. Respuesta con `search_time_ms` y lista de chunks rankeados.

## Distancia coseno vs otras métricas

- **Coseno (`<=>`):** mide ángulo entre vectores; habitual en RAG; alinea con futuro índice `vector_cosine_ops`.
- **L2 / inner product:** no usados aquí; cambiarían el ranking y el operador de índice.
- **Interpretación:** distancia **menor = más similar**. Valores ~0.4 = match razonable; ~0.65+ = similitud moderada en corpus pequeño.

## Sin índice vectorial (baseline)

Sequential scan sobre cientos de chunks es aceptable para el ejercicio. El coste visible prepara feature futura con HNSW/IVFFlat.

## Query de ejemplo analizada (manual)

**Query:** `REST API with SAML authentication for public educational sector`, `k=5`

**Observación clave:** no hay chunks con "SAML" en el corpus. El ranking mezcla:

| Rank | Sector | Componente | distance | Lectura |
|------|--------|------------|----------|---------|
| 1–2 | finance | OAuth 2.0 backend | ~0.653 | Señal auth/API domina; duplicado por doble ingest |
| 3 | education | Course catalog API | ~0.653 | Mejor match de sector + API |
| 4–5 | education | SCORM / dashboard | 0.69–0.71 | Mismo presupuesto LMS, menos relevante |

**Lecciones operativas:**

1. Búsqueda semántica ≠ keyword search.
2. Ingest duplicado ocupa slots del top-k.
3. Queries multi-señal (sector + tech + protocolo) producen rankings no obvios — hay que leer `distance` y metadata.

**Contraste:** query `OAuth authentication fintech` sobre el mismo corpus → distance ~0.42 en el chunk OAuth — match claro.

## Comandos

```bash
# Tests
uv run pytest tests/embedding_pipeline/test_search_*.py -q

# Manual (Compose + corpus ingestado)
curl -sS -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"REST API with SAML authentication for public educational sector","k":5}' \
  | python3 -m json.tool
```

## Siguiente paso

Feature-039: script `query_examples.py`, `output_examples.txt`, y sección README ampliada con cinco categorías de query.
