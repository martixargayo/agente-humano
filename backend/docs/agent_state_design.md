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

## “Por qué” (rationale por cambio)

### Belief gating por flags críticos

- **Problema observado**: si el extractor de `world_diff` falla, cambios en señales clave podían quedar sin update de belief, dejando el estado stale.
- **Invariante**: cambios en señales críticas de world state deben disparar actualización de belief aunque no haya `world_diff`.
- **Cambio implementado**: se añade un chequeo directo de flags críticos en `has_belief_evidence_delta` para forzar `True` cuando cambian.
- **Tradeoffs**: se puede actualizar más a menudo (ligero costo de latencia), pero se evita drift silencioso.
- **Cómo se observa en producción**: disminuyen los casos con cambios de flags sin actualización de belief en métricas de “belief_update_skipped”.
- **Qué test lo cubre**: se cubre indirectamente por los tests de normalización + gating existentes; no aplica un test unitario específico aún.

### Estabilidad de razones top-K (tie-break determinista)

- **Problema observado**: orden por score puro produce churn entre razones con scores similares, causando cambios no deterministas.
- **Invariante**: para scores empatados, el orden de razones debe ser determinista.
- **Cambio implementado**: se añade un orden de prioridad fijo como tie-break en el sorting de razones.
- **Tradeoffs**: prioriza señales “core” en empates, lo cual puede sesgar levemente el top-K pero mejora estabilidad.
- **Cómo se observa en producción**: se reduce el churn en `belief.reasons` entre turnos con scores cercanos.
- **Qué test lo cubre**: no aplica test unitario directo; la estabilidad se valida en regresiones de salida.

### Normalización robusta de `policy_attempts`

- **Problema observado**: valores como `"3"` se descartaban, perdiendo conteos reales.
- **Invariante**: `policy_attempts` debe aceptar enteros y strings numéricos de forma segura.
- **Cambio implementado**: coerción a `int` con captura de errores y emisión de issues por key inválida.
- **Tradeoffs**: añade validaciones por elemento; coste mínimo y mejora de compatibilidad.
- **Cómo se observa en producción**: menos resets de intentos por payloads legacy.
- **Qué test lo cubre**: cubierto por los tests de normalización existentes; no aplica un caso dedicado aún.

### Tests de planner sin IDs inventadas

- **Problema observado**: usar IDs inexistentes vuelve el test frágil ante cambios de catálogo.
- **Invariante**: los tests deben usar IDs reales del catálogo.
- **Cambio implementado**: el test usa `list_policy_ids()` para tomar IDs válidas.
- **Tradeoffs**: acopla el test al catálogo real, pero garantiza coherencia y evita falsos negativos.
- **Cómo se observa en producción**: tests más estables y menos flaky cuando se actualiza el catálogo.
- **Qué test lo cubre**: `test_allowed_policy_ids_uses_outcome_per_policy`.

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
