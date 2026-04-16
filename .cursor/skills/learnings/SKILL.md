---
name: learnings
description: Registra correcciones, gaps de conocimiento y mejores prácticas en docs/learnings. Usar cuando: (1) el usuario corrige al agente ("no, eso está mal", "en realidad..."), (2) la documentación o el conocimiento del agente resulta incorrecto o desactualizado, (3) se descubre un enfoque mejor para una tarea recurrente, (4) un bug resuelto deja una lección que debe quedar como regla. Revisar learnings pendientes antes de tareas grandes. Promover a .cursor/rules o docs cuando el learning sea aplicable de forma amplia.
---

# Learnings (sistema del proyecto)

Registro de **learnings** (no bugs ni features) en `docs/learnings/`. Inspirado en flujos de mejora continua; adaptado a la estructura del proyecto.

## Dónde vive

- **Descripción y formato:** `docs/learnings/README.md`
- **Entradas:** `docs/learnings/LEARNINGS.md` — una sola lista; apendizar cada entrada al final.

## Cuándo registrar un learning (y no un bug/feature)

| Situación | Dónde | Acción |
|-----------|--------|--------|
| Error, fallo, incoherencia | docs/bugs | `/add-bug` (skill bug-reporting) |
| Mejora o nueva capacidad | docs/features/backlog | skill feature-backlog |
| Usuario corrige ("no, eso está mal", "en realidad...") | docs/learnings | Entrada en LEARNINGS.md, categoría `correction` |
| Documentación/conocimiento desactualizado o incorrecto | docs/learnings | Entrada, categoría `knowledge_gap` |
| Enfoque mejor para tarea recurrente | docs/learnings | Entrada, categoría `best_practice` |
| Bug resuelto deja lección que debe ser regla | docs/learnings | Entrada y luego promover a regla/docs |

## Formato de entrada (append en LEARNINGS.md)

```markdown
## [LRN-YYYYMMDD-XXX] categoría

**Registrado:** YYYY-MM-DD
**Prioridad:** low | medium | high
**Estado:** pending
**Área:** cli | api | docs | config | tests | segundo_cerebro | ticktick

### Resumen
Una línea con qué se aprendió.

### Detalle
Contexto: qué pasó, qué estaba mal, qué es correcto.

### Acción sugerida
Qué hacer (ej. "Añadir a regla X", "Documentar en docs/Y").

### Metadata
- Origen: conversación | error | feedback_usuario
- Archivos: path/to/file si aplica
- Ver también: LRN-YYYYMMDD-YYY si hay relación

---
```

- **Categorías:** `correction` | `knowledge_gap` | `best_practice`
- **ID:** `LRN-YYYYMMDD-XXX` (XXX secuencial o 3 caracteres)

## Promoción a memoria del proyecto

Cuando el learning sea aplicable de forma amplia (varios archivos, cualquier colaborador o agente debería saberlo):

1. **Distilar** en una regla breve o párrafo de documentación.
2. **Añadir** a `.cursor/rules/` (nueva o sección en regla existente) o a `docs/` (p. ej. chato-cli.md).
3. **Actualizar** la entrada: `**Estado:** promoted`, añadir `**Promovido a:** .cursor/rules/nombre.mdc` (o ruta en docs).
4. Opcional: bloque `### Resolución` con fecha y archivo de destino.

## Revisión

- **Antes de tareas grandes:** revisar `docs/learnings/LEARNINGS.md` por área (cli, api, docs, etc.).
- **Patrones recurrentes:** si varias entradas se parecen, enlazar con "Ver también" y valorar promoción o fix sistémico.

## Reglas

- No duplicar: buscar por palabra clave en LEARNINGS.md antes de añadir.
- Contenido: español para prosa; inglés para código y comandos.
- Prioridad: `high` si afecta flujos comunes o se repite; `medium` si tiene workaround; `low` si es edge case.

## Referencias en el proyecto

- Formato y propósito: `docs/learnings/README.md`
- Listado: `docs/learnings/LEARNINGS.md`
