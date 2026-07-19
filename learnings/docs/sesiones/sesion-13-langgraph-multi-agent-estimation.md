# Sesión 13 — Grafo multi-agente de estimación (LangGraph)

## Objetivo pedagógico

Mostrar que un flujo de estimación multi-paso con revisión humana es un **grafo
explícito y tipado**, no una caja negra: handovers con `Command`, puertas con
`interrupt()`, fan-out con `Send`, y un reducer keyed para no duplicar horas al
reanudar.

## Qué quedó en `master-ia` (feature-066 cerrado, Steps 1–9)

| Pieza | Ubicación |
| --- | --- |
| Estado + reducer keyed | `app/services/estimation_graph/state.py` |
| Compilación del grafo | `app/services/estimation_graph/build.py` |
| Checkpointer Postgres | `app/services/estimation_graph/checkpointer.py` + lifespan → `app.state.graph` |
| Agentes / puertas | `app/services/estimation_graph/agents/*` |
| Activity feed (stream) | `app/services/estimation_graph/activity.py` |
| Agentes S12 en dos fases | `run_structure_agent`, `run_task_hours_recovery_agent` |
| HTTP | `POST/GET /api/v1/estimate/graph*` (start, resume, state, stream, progress, proposal) |
| CLI entregable | `app/scripts/run_graph_s13.py` |
| Ejercicio | `exercises/session-13/` |
| Tests MemorySaver + router | `tests/estimation_graph/`, `tests/routers/test_estimate_graph.py` |

**Deferred (follow-up):** React wizard (AC-13 / Step 10) via `/write-front-feature`.

## Topología en vivo

```text
classifier → structure → 🧑 gate 1 → Send×N hours → recover → analysis → 🧑 gate 2 → proposal?
```

## Decisiones de fork (no “arreglar” sin ADR)

1. **Paquete en `app/services/estimation_graph/`** — sin inventar `app/domain/`.
2. **Logging stdlib** — sin `structlog`.
3. **LLM estructurado** — `complete_graph_structured` (Instructor/LiteLLM), no `LLMWrapper`.
4. **Structure / recovery** — Responses API directa (misma excepción que feature-054).
5. **Superficie aditiva** — agent / RAG / CAG intactos; grafo caído → 503 solo en rutas graph.

## Comandos

```bash
# Smoke parcial offline (sin Postgres; horas enlatadas; necesita OPENAI_API_KEY)
uv run python app/scripts/run_graph_s13.py --memory --stub

# Informe local (no commitear)
uv run python app/scripts/run_graph_s13.py --memory --stub \
  --out /tmp/example_run_complex.txt

# Path completo (checkpointer Postgres + retrieval real; stack up + corpus)
uv run python app/scripts/run_graph_s13.py \
  --out /tmp/example_run_complex.txt
```

## Tests (sin API key en CI)

```bash
uv run pytest tests/estimation_graph tests/routers/test_estimate_graph.py \
  tests/services/agentic tests/exercises/test_session_13_assets.py -q
```

## Documentación técnica

- Referencia: [docs/technical/estimation-graph-s13.md](../../../docs/technical/estimation-graph-s13.md)
- Work item: [feature-066-langgraph-multi-agent-estimation-s13.md](../../../docs/work-items/feature-066-langgraph-multi-agent-estimation-s13.md)
- Repo oficial: rama `session_13_live` en `ai-engineering`
