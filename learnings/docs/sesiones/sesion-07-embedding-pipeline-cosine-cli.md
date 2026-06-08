# Sesión 07 — CLI cosine similarity (feature-034)

## Qué se hizo

- CLI `python -m app.scripts.compare` con `--text-a` / `--text-b`.
- Similitud coseno manual con `math` (sin numpy).
- Reutiliza `OpenAIEmbedder.embed_one()` envuelto en `asyncio.run`.
- Sanity check documentado en `app/embedding_pipeline/SANITY_CHECK.md`.

## Resultados del sanity check

| Par | Similitud | Notas |
|-----|-----------|-------|
| A (auth/JWT cercano) | 0.5957 | Apenas bajo el umbral 0.6 del ejercicio |
| B (auth vs migración DB) | 0.1920 | Claramente bajo 0.4 |
| C (genérico) | 0.5408 | Ambiguo — buen material de discusión |

## Aprendizaje

- `text-embedding-3-small` separa bien dominios distintos (Par B) pero textos cortos o genéricos (Par C) dan scores intermedios difíciles de interpretar sin contexto.
- El Par A muestra que umbrales fijos (0.6) son orientativos: variaciones de redacción mueven el score unos puntos.
- Mantener el script bajo `app/scripts/` permite ejecutarlo dentro del contenedor Docker (`COPY app ./app`).
- Cierra el milestone Session 07: schemas → chunker → embedder → endpoint → sanity check.

## Siguiente

- Session 08: persistencia en vector DB (fuera de scope actual).
