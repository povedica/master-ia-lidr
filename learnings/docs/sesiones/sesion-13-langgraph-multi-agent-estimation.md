# Sesión 13 — Grafo multi-agente de estimación (LangGraph)

## Objetivo pedagógico

Mostrar que un flujo de estimación multi-paso con revisión humana es un **grafo
explícito y tipado**, no una caja negra: handovers con `Command`, puertas con
`interrupt()`, fan-out con `Send`, y un reducer keyed para no duplicar horas al
reanudar.

## Qué quedó en `master-ia` (hasta Step 7)

| Pieza | Ubicación |
| --- | --- |
| Estado + reducer keyed | `app/services/estimation_graph/state.py` |
| Compilación del grafo | `app/services/estimation_graph/build.py` |
| Agentes / puertas | `app/services/estimation_graph/agents/*` |
| Agentes S12 en dos fases | `run_structure_agent`, `run_task_hours_recovery_agent` |
| CLI entregable | `app/scripts/run_graph_s13.py` |
| Ejercicio | `exercises/session-13/` |
| Tests MemorySaver | `tests/estimation_graph/` |

Pendiente de otros steps: checkpointer Postgres + lifespan (`app.state.graph`),
router HTTP `/api/v1/estimate/graph*`, stream/progress, wizard React.

## Topología en vivo

```text
classifier → structure → 🧑 gate 1 → Send×N hours → recover → analysis → 🧑 gate 2 → proposal?
```

## Decisiones de fork (no “arreglar” sin ADR)

1. **Paquete en `app/services/estimation_graph/`** — sin inventar `app/domain/`.
2. **Logging stdlib** — sin `structlog`.
3. **LLM estructurado** — `complete_graph_structured` (Instructor/LiteLLM), no `LLMWrapper`.
4. **Structure / recovery** — Responses API directa (misma excepción que feature-054).
5. **Superficie aditiva** — agent / RAG / CAG intactos.

## Comandos

```bash
# Smoke parcial offline (sin Postgres; horas enlatadas; necesita OPENAI_API_KEY)
uv run python app/scripts/run_graph_s13.py --memory --stub

# Informe local (no commitear)
uv run python app/scripts/run_graph_s13.py --memory --stub \
  --out /tmp/example_run_complex.txt
```

Tras Step 5, el path completo usa el checkpointer de Postgres (sin `--memory`).

## Tests (sin API key en CI)

```bash
uv run pytest tests/estimation_graph tests/exercises/test_session_13_assets.py -q
```

## Documentación técnica

- Referencia: [docs/technical/estimation-graph-s13.md](../../../docs/technical/estimation-graph-s13.md)
- Work item: [feature-066-langgraph-multi-agent-estimation-s13.md](../../../docs/work-items/feature-066-langgraph-multi-agent-estimation-s13.md)
- Repo oficial: rama `session_13_live` en `ai-engineering`
