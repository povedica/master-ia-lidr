# commit-pending

## Propósito

Crear commits pequeños, claros y trazables para `master-ia`, siempre vinculados a una sesión del máster y documentados en `second-brain-master-ia`.

## Cuándo usar

- Cuando hay cambios pendientes y quieres cerrarlos con commits ordenados.
- Después de actualizar notas, arquitectura o documentación con `/update-docs`.
- Cuando quieres dejar trazabilidad académica de lo que se hizo en una sesión concreta.

## Reglas del proyecto

- **Sesión obligatoria:** no se hace ningún commit sin saber a qué sesión pertenece (`sesion-01-llms-setup`, `[[sesiones/...]]` o equivalente).
- **Tamaño:** objetivo de hasta **5 archivos** y **~200 líneas** por commit, salvo que el cambio pida otra cosa.
- **Mensajes:** en **inglés**, con prefijo convencional: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- **Documentación del commit:** cada commit debe quedar registrado en la nota de sesión con una tabla:

| Hash (corto) | Mensaje | Qué aporta / alcance funcional |
|--------------|---------|--------------------------------|

La **tabla se escribe en español**, aunque el commit vaya en inglés.

---

## Flujo obligatorio

### Fase 0. Identificar la sesión

Antes de hacer nada, identifica la sesión de trabajo:

- `second-brain-master-ia/sesiones/sesion-NN-*.md`
- o un enlace tipo `[[sesiones/sesion-01-llms-setup]]`

Si no está clara, **para y pregunta**.

### Fase 1. Revisar el estado pendiente

```bash
git status
git status --short
git diff --stat
```

Anota:

- archivos modificados, nuevos y borrados
- si hay mezcla de código, docs y configuración
- si conviene dividir en más de un commit

### Fase 2. Detectar archivos que no deben entrar

Revisa si hay ficheros que deberían ir a `.gitignore` en lugar de a Git:

- secretos: `.env`, `.env.local`, credenciales, tokens
- caches o runtime: `.venv/`, `__pycache__/`, `*.pyc`, logs
- artefactos locales: `.DS_Store`, `.idea/`, `Thumbs.db`
- ficheros de usuario si no se quieren versionar

Si detectas alguno:

1. Informa al usuario antes de seguir.
2. Propón añadirlo a `.gitignore`.
3. No lo incluyas en ningún commit hasta resolverlo.

### Fase 3. Agrupar commits

Agrupa cambios por foco:

- `feat`: funcionalidad nueva
- `fix`: corrección
- `docs`: README, comandos Cursor, notas técnicas
- `test`: nuevas pruebas o ampliaciones
- `chore`: tooling, Docker, config, housekeeping
- `refactor`: mejora interna sin cambio funcional esperado

Escribe primero el plan de commits: mensaje tentativo + archivos por commit.

### Fase 4. Quality gates

No inventes validaciones que el repo no tiene. Usa solo las que apliquen a `master-ia`.

#### Si tocaste Python o dependencias

```bash
uv sync
```

Si existe un comando de tests en el futuro, ejecútalo también.

#### Si tocaste Docker

```bash
docker compose config
```

Y si el cambio afecta a build o runtime:

```bash
docker compose build
```

#### Si no hay suite automatizada

Decláralo explícitamente en tu razonamiento y haz una verificación manual mínima si aplica:

- revisar `app/`
- comprobar arranque de FastAPI
- validar que el README o la documentación no contradicen el comportamiento real

### Fase 5. Commit

Para cada grupo:

1. `git add` solo de los archivos de ese commit.
2. Crear el commit con mensaje semántico en inglés.
3. Obtener el hash corto:

```bash
git rev-parse --short HEAD
```

4. Actualizar la sesión correspondiente en `second-brain-master-ia/sesiones/` con una fila en `## Commits del repositorio (master-ia)` o una sección equivalente.

Ejemplos de mensajes:

- `feat(api): add study endpoint scaffold`
- `fix(docker): copy readme before uv sync`
- `docs(cursor): align cursor commands with master ia workflow`
- `chore(repo): add cursor plans directory`

### Fase 6. Verificación final

```bash
git status
git log --oneline -n 10
```

Comprueba:

- árbol limpio o con restos intencionados
- commits claros y pequeños
- tabla de la sesión actualizada con todos los hashes generados

---

## Plantilla de tabla para la sesión

Pega o actualiza esto en la nota de sesión si aún no existe:

```markdown
## Commits del repositorio (master-ia)

| Hash (corto) | Mensaje | Qué aporta / alcance funcional |
|--------------|---------|--------------------------------|
| `abc1234` | `docs(cursor): align cursor commands with master ia workflow` | Unifica comandos en `.cursor/commands/` y enlaces internos. |
```

## Checklist

- [ ] La sesión está identificada.
- [ ] No hay secretos ni artefactos locales en staging.
- [ ] Cada commit tiene un solo foco razonable.
- [ ] Se han corrido las validaciones que aplican de verdad.
- [ ] Cada commit ha quedado documentado en la nota de sesión.

## Relacionado

- [`update-docs`](update-docs.md)
- [`session-review`](session-review.md)
- [`master-tutor`](master-tutor.md)

**Última actualización:** 2026-04-15
