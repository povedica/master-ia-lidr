# commit-pending

## Propósito

Crear commits pequeños, claros y trazables para `master-ia`, vinculados a la **sesión del máster** y a la **feature activa**, y documentar cada commit en el sitio acordado (prioridad: documento de la feature).

## Cuándo usar

- Cuando hay cambios pendientes y quieres cerrarlos con commits ordenados.
- Después de actualizar notas, arquitectura o documentación con `/update-docs`.
- Cuando quieres dejar trazabilidad académica de lo que hiciste en una sesión o en una feature concreta.

## Reglas del proyecto

- **Documento de feature (prioritario):** el reporte de commits debe añadirse al documento de la feature que esté en curso, cuando exista y esté claro (por convención: `second-brain-master-ia/proyectos/<proyecto>/decisiones/feature-*.md` o ruta explícita que indiques).
- **Sesión del máster:** sigue siendo obligatoria la vinculación a una sesión (`second-brain-master-ia/sesiones/sesion-NN-*.md` o enlace) para contexto y tabla duplicada o resumen, **si** aplica; si el trabajo es solo de una feature, la tabla principal puede vivir **solo** en el doc de la feature.
- **Si no está claro dónde anotar:** **no hagas `git commit` sin antes preguntar** al usuario en qué documento(s) quiere el reporte. Siempre ofrece una **sugestión explícita por defecto**, por ejemplo:
  - *"Sugiero anotar la tabla de commits en `second-brain-master-ia/proyectos/<proyecto>/decisiones/<feature-activa>.md` y, si quieres trazabilidad de clase, un resumen en `sesiones/sesion-NN-*.md`."*
- **Tamaño:** objetivo de hasta **5 archivos** y **~200 líneas** por commit, salvo que el cambio sea un bloque lógico indivisible (p. ej. scaffold inicial) y se documente en el propio reporte.
- **Mensajes:** en **inglés**, con prefijo convencional: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- **Tabla de commits:** se escribe en **español** (columna de descripción), aunque el mensaje del commit vaya en inglés.

## Tabla estándar (pegar en el documento de destino)

```markdown
## Commits del repositorio (master-ia)

| Hash (corto) | Mensaje | Qué aporta / alcance funcional |
|--------------|---------|--------------------------------|
| `abc1234` | `docs(cursor): example message` | Breve descripción en español. |
```

**Destino prioritario:** el archivo de la feature en curso (p. ej. `decisiones/feature-configuracion-inicial-cag.md`). **Secundario opcional:** la nota de sesión activa, con enlace a la feature si no quieres duplicar filas.

---

## Flujo obligatorio

### Fase 0. Identificar documentación del reporte (feature + sesión)

1. **Feature activa:** identifica el documento canónico de la feature (p. ej. bajo `second-brain-master-ia/proyectos/estimador-cag/decisiones/`). Ese es el sitio **por defecto** para la sección `## Commits del repositorio (master-ia)`.
2. **Sesión:** localiza `second-brain-master-ia/sesiones/sesion-NN-*.md` si aplica a este trabajo.
3. **Si falta el doc de la feature o hay ambigüedad:** detente, **pregunta** al usuario dónde anotar el reporte e incluye **siempre** una sugerencia concreta (rutas de ejemplo anteriores). No ejecutes `git commit` hasta tener respuesta o confirmación explícita del destino.

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

Si existe un comando de tests, ejecútalo también.

#### Si tocaste Docker

```bash
docker compose config
```

Y si el cambio afecta a build o runtime:

```bash
docker compose build
```

#### Si no hay suite automatizada

Decláralo explícitamente y haz una verificación manual mínima si aplica.

### Fase 5. Commit

Para cada grupo:

1. `git add` solo de los archivos de ese commit.
2. Crear el commit con mensaje semántico en inglés.
3. Obtener el hash corto:

```bash
git rev-parse --short HEAD
```

4. **Añade una fila a la tabla** en el **documento de la feature** acordado en Fase 0 (obligatorio cuando la feature esté identificada).
5. Si aplica, actualiza la sesión con un resumen o enlace a la feature para no duplicar tablas.

Ejemplos de mensajes:

- `feat(api): add study endpoint scaffold`
- `fix(docker): copy readme before uv sync`
- `docs(cursor): add estimador-cag rules and commands`
- `chore(repo): add cursor plans directory`

### Fase 6. Verificación final

```bash
git status
git log --oneline -n 10
```

Comprueba:

- árbol limpio o con restos intencionados
- commits claros y pequeños
- tabla de la feature (y, si aplica, sesión) actualizada con todos los hashes

### Fase 7. Push al remoto

```bash
git push -u origin HEAD
```

Si el remoto rechaza el push, sincroniza con `git pull --rebase` y vuelve a `git push`.

---

## Regla de oro (reporte de commits)

| Situación | Acción |
|-----------|--------|
| Feature conocida | Actualiza **siempre** `## Commits del repositorio (master-ia)` en el `.md` de esa feature. |
| Feature desconocida | **Pregunta** dónde anotar; **sugiere** `decisiones/feature-<nombre>.md` bajo el proyecto en Second Brain, o `sesiones/sesion-NN-*.md` como secundario. |
| Trabajo mezclado (master-ia + notas fuera del repo) | Commitea solo lo que vive en el repo; el reporte de tabs puede vivir en Second Brain aunque esos archivos no estén en `git` (sigue siendo el destino del reporte). |

## Checklist

- [ ] Destino del reporte de commits acordado (feature doc por defecto, o pregunta + sugerencia hecha).
- [ ] No hay secretos ni artefactos locales en staging.
- [ ] Cada commit tiene un solo foco razonable.
- [ ] Se han corrido las validaciones que aplican.
- [ ] Cada commit quedó en la **tabla del documento de la feature** (o en el acordado).
- [ ] `git push` a `origin` realizado o error explicado.

## Relacionado

- [`update-docs`](update-docs.md)
- [`session-review`](session-review.md)
- [`master-tutor`](master-tutor.md)

**Última actualización:** 2026-04-26
