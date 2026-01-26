# Diseño de estado del agente (StateAct-like, 2026)

## Por qué estos cambios

- **Normalización tolerante (non-strict)**: se evita que un campo inválido (p. ej. tono) resetee el estado completo, reduciendo discontinuidades que confundían al planner y a las métricas de progreso.
- **Temporalidad correcta (executed vs chosen)**: se separa lo ejecutado de lo elegido, garantizando que el estado persistente refleje acciones realmente ejecutadas.
- **Fallback explícito y trazable**: cuando hay datos inválidos (e.g. `policy_id`), se registra el issue y se aplica un fallback declarado, evitando “autocorrecciones” silenciosas.
- **Estabilidad**: se usa gating por deltas (world_diff + cambios de tono) y smoothing en updates, reduciendo oscilaciones y loops falsos.
- **Source of truth único**: se elimina ambigüedad de campos duplicados, mejorando trazabilidad de debugging y coherencia en el wiring.

### Riesgos eliminados

- **Early return en normalización** → evitaba aplicar el resto del estado → *planner errático/estados discontinuos*.
- **Outcome global por turno** → penalizaba policies no responsables → *bloqueos injustificados*.
- **Campos ambiguos (`last_policy_id`)** → conflicto entre “chosen” y “executed” → *temporalidad inconsistente*.

### Métricas observables que mejoran

- Menos loops falsos por penalización global de outcomes.
- Menor drift por normalización tolerante y smoothing.
- Mayor trazabilidad (issues + `policy_last_outcome`).

### Tradeoffs

- **Costo**: más campos en `ProgressState` y validaciones adicionales.
- **Beneficio**: mayor estabilidad y claridad diagnóstica en producción.

## Changelog técnico (deprecaciones y migración)

- **Deprecado**: `last_policy_id` (ambigüo). Se mantiene solo para compatibilidad de sesiones antiguas.
  - **Migración**: `last_policy_id` se mapea a `last_chosen_policy_id` y `last_executed_policy_id` en normalización.
- **Nuevo**: `policy_last_outcome` (mapa `policy_id → outcome`) para gating por policy.
- **Persistencia**: `last_policy_executed` es la única fuente de verdad para el outcome ejecutado por turno.

## Compatibilidad con sesiones antiguas

- `last_policy_executed = {}` o sin `policy_id` se trata como `None`.
- `last_policy_outcome` legado se mapea a `last_executed_policy_outcome`.
- `last_policy_id` legado se mapea a `last_chosen_policy_id` y `last_executed_policy_id`.

## Alineación con prácticas/papers

- **Temporalidad correcta**: separación estricta de *chosen* vs *executed*.
- **Fallback explícito** ante acciones inválidas.
- **Normalizers tolerantes** con modo strict opcional.
- **Delta updates + smoothing** para estabilidad.
- **Source of truth único** para evitar wiring ambiguo.
