# 05 · Fase 4 — Memoria, compresión diferida y endurecimiento

## 1) Alcance

Implementar política V1 de memoria ya decidida:
- trimming determinista `recent_dialogue`,
- compresión diferida,
- fallback determinista,
- observabilidad y pruebas largas.

---

## 2) Diseño operativo concreto

## 2.1 Qué va en camino crítico (runtime principal)

1. Update de `recent_dialogue` + trimming.
2. Append de `memory_episodic` desde `BrainOutput`.
3. Evaluación de necesidad de compresión (solo **schedule**, no ejecutar compresión pesada inline).
4. Registro de estado/trace de scheduling.

## 2.2 Qué va fuera del camino crítico

1. Ejecución de compresión diferida.
2. Reintentos de compresión.
3. Reconciliación de `memory_compacted_summary`.

---

## 3) Mecanismo diferido propuesto (concreto, V1)

### Hecho observado

No existe en repo una infraestructura de cola general explícita para trabajos diferidos de negociación; sí existen patrones de scripts/tareas y ejecución en servicios con locking/sesión.

### Decisión V1

Usar mecanismo mínimo **in-process deferred worker** por instancia, con persistencia de “pendiente” en session world_state:

1. En turno, si hay trigger, marcar:
   - `world_state["conversation_simple_memory_maintenance"]["pending"] = true`
   - metadata (`scheduled_at`, `reason`, `attempts`).
2. Ejecutar compresión en background best-effort tras responder (threadpool no bloqueante) **o** en siguiente turno si quedó pendiente.
3. Si proceso cae, el estado pending persiste en session store y se reintenta en turno futuro.

### Por qué este mecanismo

- No requiere infraestructura externa nueva en V1.
- Mantiene latencia de turno.
- Compatible con store existente (Redis/InMemory).

---

## 4) Archivos nuevos a crear (propuestos)

- `backend/conversacion_simple/memory/__init__.py`
- `backend/conversacion_simple/memory/policy.py`
- `backend/conversacion_simple/memory/compression.py`
- `backend/conversacion_simple/memory/fallback.py`
- `backend/conversacion_simple/memory/maintenance.py`

## Funciones propuestas

- `trim_recent_dialogue(messages, max_recent_messages)`
- `should_schedule_memory_compaction(canonical_state, limits) -> Decision`
- `schedule_memory_compaction(state, reason)`
- `run_memory_compaction_deferred(state, config)`
- `apply_compaction_result(canonical_state, compaction_result)`
- `build_deterministic_compaction_fallback(canonical_state)`
- `record_memory_maintenance_trace(trace, event)`

---

## 5) Archivos existentes a modificar (propuestos)

- `backend/conversacion_simple/orchestration/flow_config.py`
  - integrar hooks de trimming/schedule/fallback logging.
- `backend/conversacion_simple/state/canonical_state.py`
  - agregar `memory_compacted_summary` + metadata de maintenance.
- `backend/conversacion_simple/traces/models.py`
  - campos observables de mantenimiento memoria.
- `backend/conversacion_simple/traces/builders.py`
  - builder de eventos de compresión.

> No tocar runtime `backend/negociacion/orchestration/flow_config.py` en esta fase.

---

## 6) Trigger de compresión (V1)

## Regla primaria

- si `len(memory_episodic) > episodic_high_res_limit` (ej: 40), programar compresión.

## Regla secundaria

- si tamaño serializado de memoria supera umbral de chars/tokens aproximado, programar compresión.

## Reglas de seguridad

- cooldown mínimo entre compresiones por sesión.
- max reintentos por ventana.

---

## 7) Fallback determinista

Si compresión diferida falla o no se ejecuta dentro de SLA:

1. construir resumen determinista desde eventos antiguos (template conservador),
2. actualizar `memory_compacted_summary`,
3. marcar `compression_mode = deterministic_fallback` y reason code.

**Importante:** nunca bloquear respuesta de turno por compresión.

---

## 8) Observabilidad obligatoria

En traces/logs de `conversacion_simple` registrar:

- `memory_recent_dialogue_count_before/after`
- `memory_recent_dialogue_trimmed_count`
- `memory_episodic_count_before/after`
- `memory_compaction_scheduled` (bool)
- `memory_compaction_mode` (`deferred_llm`, `deterministic_fallback`, `none`)
- `memory_compaction_status` (`scheduled`, `executed`, `failed`, `fallback_applied`, `skipped`)
- `memory_compaction_reason`
- `memory_growth_anomaly_flag`

---

## 9) Qué pasa si la infraestructura diferida aún no está lista

### Plan mínimo de implementación en esta fase

1. habilitar pending-state persistente,
2. ejecutar compresión de forma oportunista al inicio de turnos siguientes,
3. aplicar fallback determinista si no se pudo completar en N intentos.

Con esto se cumple V1 sin bloquear salida ni exigir worker externo.

---

## 10) Tests de Fase 4

1. `test_recent_dialogue_trim_policy_applied`.
2. `test_compaction_scheduled_when_threshold_exceeded`.
3. `test_deferred_compaction_executes_without_blocking_turn`.
4. `test_deferred_compaction_failure_triggers_deterministic_fallback`.
5. `test_memory_growth_anomaly_flag_when_limits_exceeded`.
6. `test_long_conversation_state_stability_with_compaction`.
7. `test_trace_contains_memory_maintenance_fields`.

---

## 11) Riesgos de Fase 4

1. Ejecución diferida in-process no distribuida (si múltiples réplicas).
2. Calidad variable del fallback determinista.
3. Sobrecarga de mantenimiento en turnos muy frecuentes.

### Mitigaciones

- feature flag de compresión diferida,
- límites de retries/cooldown,
- métricas de tasa de fallback y crecimiento de memoria,
- roadmap posterior para worker externo si escala lo exige.

---

## 12) Criterio de Done de Fase 4

- Política V1 de memoria implementada y validada en tests largos.
- Turno no bloquea por compresión.
- Fallback determinista demostrado ante fallos.
- Observabilidad completa de mantenimiento de memoria en traces.
- Sin regresiones funcionales en `conversacion_simple` ni `negociacion`.
