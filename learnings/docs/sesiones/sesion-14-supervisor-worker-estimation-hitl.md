# Sesión 14 — Supervisor/workers + HITL condicional

## Qué aprendí

- Un grafo multi-agente ya existe en S13, pero **supervisor/workers** hace
  explícitas las decisiones de routing (`Command(goto, update)`), el privilegio
  por worker y la evidencia acumulada.
- “Worker puro” en este contexto significa **contrato de nodo tipado**
  (state → partial update), no ausencia de I/O. Las tools se inyectan.
- “No matches” debe registrarse como búsqueda completada; si no, el supervisor
  puede ciclar entre search y sí mismo.
- No escribir canales con reducer **antes** de `interrupt()`: LangGraph
  re-ejecuta el nodo al resume.
- Tras un `adjust`, hace falta una regla acotada (`human_adjustment_validated`)
  para no reentrar en HITL infinitamente.
- `state` (ciclo de vida del checkpointer) y `status` (resultado de negocio)
  son campos distintos; no fusionarlos.

## Superficie entregada

- Topología en `app/services/estimation_graph/`
- HTTP `/api/v1/estimate/graph*` con resume tipado
- `GRAPH_HUMAN_REVIEW_CONFIDENCE_THRESHOLD=0.70`
- Ejercicio: `exercises/session-14/sample_transcript_edge_case.txt`

## Cómo verificar offline

```bash
uv run pytest tests/estimation_graph tests/routers/test_estimate_graph.py -q
uv run python app/scripts/run_graph_s13.py --memory --stub \
  --transcript exercises/session-14/sample_transcript_edge_case.txt \
  --out /tmp/supervisor_hitl_edge_case_trace.txt
```

## Referencias

- Work item: `docs/work-items/feature-067-supervisor-worker-estimation-hitl.md`
- Técnico: `docs/technical/estimation-graph-s14.md`
