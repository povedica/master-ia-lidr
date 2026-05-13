# update-docs

## Propósito

Sincronizar la documentación viva del Máster IA entre el repo y `learnings/second-brain-master-ia`, de forma que cada sesión deje rastro útil: qué se hizo, qué se decidió, qué se aprendió y qué queda pendiente.

## Cuándo usar

- Tras implementar una feature o cambiar Docker, `uv`, FastAPI, estructura del repo o comandos Cursor.
- Cuando se hayan tomado decisiones técnicas o de arquitectura.
- Cuando quieras dejar el trabajo de una sesión reflejado en el Second Brain.
- Cuando el usuario pida “documenta lo hecho”, “actualiza notas” o “deja esto registrado en la sesión”.

## Entrada

Acepta lenguaje natural. Ejemplos:

- "Actualiza la documentación de la sesión 1"
- "Documenta lo que hemos cambiado en Docker y Cursor"
- "Deja registradas las decisiones de arquitectura de hoy"

---

## Flujo obligatorio

### 1. Identificar la sesión activa

Busca primero si el contexto deja clara la sesión:

- `learnings/second-brain-master-ia/sesiones/sesion-NN-*.md`
- referencias en la conversación
- el trabajo reciente del repo

Si no está claro, pregunta antes de escribir.

### 2. Revisar avances recientes

Antes de editar, revisa:

- diffs y commits recientes del repo
- cambios en `README.md`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `app/`
- cambios en `.cursor/commands/`, `.cursor/skills/`, `.cursor/agents/`, `.cursor/plans/`
- cualquier nota de sesión ya modificada durante la conversación

Lista mental o explícitamente:

- qué se implementó
- qué se decidió
- qué se verificó
- qué queda pendiente

### 3. Elegir el destino documental correcto

Actualiza solo lo que corresponda:

| Ámbito | Dónde documentarlo | Qué va ahí |
|--------|--------------------|------------|
| Sesión activa | `learnings/second-brain-master-ia/sesiones/sesion-NN-*.md` | avances, práctica, decisiones, dudas, retrospectiva, tabla de commits |
| Plan global del curso | `learnings/second-brain-master-ia/plan-sesiones.md` | solo cambios de calendario, convención o estructura del seguimiento |
| Aprendizaje transversal | `learnings/second-brain-master-ia/aprendizajes/` | conceptos, glosario, herramientas, patrones reutilizables |
| Arquitectura / ADR cortos | Sección en la sesión activa; si es transversal, `learnings/second-brain-master-ia/aprendizajes/` o nota dedicada bajo `aprendizajes/` | decisiones con contexto, alternativas descartadas y consecuencias |
| Documentación técnica del repo | `README.md` | setup, uso del proyecto, comandos, estructura del repo |
| Notas del proyecto **estimador-cag** en Second Brain | `learnings/second-brain-master-ia/proyectos/estimador-cag/` (canónico); réplicas en git: `docs/`, `learnings/docs/sesiones/`, `learnings/aprendizajes/`, `learnings/retrospectiva/` | tras editar el vault, ejecutar `bash scripts/sync-estimador-cag-docs.sh` desde la raíz del repo |
| Planes del trabajo | `.cursor/plans/` | planes de ejecución que convenga conservar dentro del repo |
| Comandos, skills y subagentes de Cursor | `.cursor/commands/`, `.cursor/skills/`, `.cursor/agents/` | automatizaciones y flujos internos del proyecto |

### 4. Regla de prioridad documental

Para evitar duplicidad:

1. **Primero** documenta en la sesión activa.
2. **Después**, si el contenido vale para varias sesiones, promuévelo a `aprendizajes/`.
3. Solo actualiza `README.md` si el cambio afecta al uso real del repo.

### 5. Qué debe quedar registrado por sesión

Siempre que aplique, deja rastro de:

- cambios funcionales en el repo
- decisiones de arquitectura o tooling
- verificaciones realizadas
- comandos importantes ejecutados
- bloqueos, dudas o siguientes pasos
- commits generados en esa sesión

Si una decisión técnica es relevante, no la dejes solo en el commit: escríbela también en la nota de sesión con contexto y motivo.

### 6. Reglas de escritura

- Prosa en español.
- Código, rutas, comandos y nombres técnicos en inglés cuando corresponda.
- No repitas un README entero en varias notas si basta con un resumen y un enlace.
- Si hay varias piezas en la misma sesión, agrúpalas por secciones claras:
  - `## Avances y práctica`
  - `## Decisiones técnicas`
  - `## Commits del repositorio (master-ia)`
  - `## Dudas / seguimiento`

### 7. Verificación

Tras editar:

- comprueba que la sesión correcta quedó actualizada
- revisa que no se haya documentado en dos sitios lo mismo sin necesidad
- confirma que las rutas citadas existen
- si tocaste README o comandos, verifica que no contradicen el comportamiento real del repo
- si tocaste `learnings/second-brain-master-ia/proyectos/estimador-cag/`, ejecuta `bash scripts/sync-estimador-cag-docs.sh` y revisa el diff bajo `docs/` y `learnings/`

---

## Checklist por tipo de cambio

**Cambio técnico en el repo**

- [ ] `README.md` si cambia setup, ejecución o estructura del proyecto.
- [ ] nota de sesión activa en `learnings/second-brain-master-ia/sesiones/`.

**Cambio de arquitectura o decisión relevante**

- [ ] nota de sesión con contexto, decisión y motivo.
- [ ] promoción a `aprendizajes/` si la idea es transversal.

**Cambio en comandos, skills o subagentes de Cursor**

- [ ] archivo del comando, skill o subagente actualizado.
- [ ] nota de sesión con el impacto práctico en el flujo de trabajo.

**Nuevos aprendizajes del curso**

- [ ] nota de sesión con el ejemplo o contexto.
- [ ] archivo en `learnings/second-brain-master-ia/aprendizajes/` si merece consolidación.

**Cambios en notas del estimador-cag (`learnings/second-brain-master-ia/proyectos/estimador-cag/`)**

- [ ] `bash scripts/sync-estimador-cag-docs.sh` desde la raíz del repo y revisar el diff en `docs/` y `learnings/`.

---

## Resolución

Al terminar, responde con:

1. Archivos actualizados.
2. Qué quedó documentado en cada uno.
3. Qué no se tocó y por qué.

## Relacionado

- [`commit-pending`](commit-pending.md)
- [`session-review`](session-review.md)
- [`master-tutor`](master-tutor.md)

**Última actualización:** 2026-04-15
