# File Snapshot

Original path:
`backend/negociacion/ARCHITECTURE_VALIDATION_REPORT.md`

Snapshot status:
`current`

Language / type:
`markdown`

```markdown
# Architecture Validation Report

## Correcciones implementadas en esta intervención

### 1) `flow_config.py`: endurecimiento del wiring sin rediseño
Se mantuvo `flow_config.py` como orquestador, pero se hicieron ajustes concretos para bajar riesgo operativo:

- Se eliminaron piezas redundantes/no usadas (`_resolve_structured_result` y su `TypeVar` asociado).
- Se agregó helper explícito para ejecutar memory+phase por modo de threading: `_execute_memory_and_phase(...)`.
- Se separó la resolución de outputs de memory y phase en helpers dedicados:
  - `_resolve_memory_call_result(...)`
  - `_resolve_phase_call_result(...)`
- Se agregó recolección de razones de rechazo/seguridad con deduplicación:
  - `_append_unique_reason(...)`
  - `_collect_last_refusals(...)`

Resultado: el wiring crítico (llamadas memory/phase, aplicación de outputs, contexto OpenAI y trazabilidad de refusals) queda explícito y verificable por tests.

### 2) Bug de `previous_response_id` + paralelización
Se corrigió de forma explícita:

- `ThreadMode.conversation`: memory + phase classifier siguen en paralelo.
- `ThreadMode.previous_response_id`: memory y phase classifier se ejecutan en secuencia deliberada para no compartir parent ambiguo.

Cadena determinista en `previous_response_id`:
1. call memory con parent actual
2. update thread con response memory
3. refresh context
4. call phase classifier con nuevo parent
5. update thread con response phase
6. refresh context

Esto evita forks implícitos sobre el mismo `previous_response_id`.

### 3) `trace.last_refusals` completo y honesto
Antes solo recogía refusals de logs de modelo.
Ahora `last_refusals` agrega y deduplica:

1. refusal de modelo (si existe)
2. `executor_output.refusal_reason` final (si existe)
3. razón de intervención de guardrail (`enforcement_reason`) cuando aplica

Esto cubre tanto refusals directos como reescrituras/restricciones de seguridad.

### 4) Fallback de `StateRepository.load_state()` conserva identidad real
Se corrigió el fallback para estado canónico corrupto/inválido:

- Ya no reconstruye siempre con `pending_session`.
- Usa `session_state.session_id` y `session_state.user_id` cuando existen.
- `pending_session` queda solo para casos sin identidad disponible.

### 5) `ensure_openai_thread()` simplificado (sin fallback fantasma)
Se limpió la lógica redundante basada en `or mode_default`.

- El modo efectivo se toma del canónico válido (`canonical_state.openai_thread.thread_mode`).
- Se mantiene bootstrap de conversación solo cuando corresponde.
- En `previous_response_id` no se resetea modo ni parent por configuración externa.

### 6) Limpieza real de `shared_types.py`
Se auditó uso y se eliminaron enums no usados en la arquitectura actual:

- `PlannerStatus`
- `ExecutorStatus`
- `ConversationAct`
- `LengthBand`
- `DirectnessLevel`
- `InitiativeLevel`
- `EmotionalIntensity`
- `SafetyRiskLevel`

Se mantuvieron los enums efectivamente usados por el flujo actual (`ThreadMode`, `NodeName`, `NegotiationPhase`, `SafetyPolicyAction`, `SafetyDomain`, `StyleTone`, `StructuredCallSource`, `SDKCompatibilityStatus`).

## Validación ejecutada

Suite principal actualizada:
- `backend/tests/test_negotiation_architecture_clean.py`

Cobertura relevante añadida/reforzada:

1. **Threading / previous_response_id**
   - paralelo permitido en `conversation`
   - secuencial obligatorio en `previous_response_id`
   - verificación de orden de llamadas y `request_context` por llamada
   - encadenamiento determinista de `previous_response_id`

2. **`trace.last_refusals`**
   - refusal de modelo
   - guardrail de rewrite
   - refusal_reason final de executor
   - guardrail de dominio
   - deduplicación de razones repetidas
   - vacío en happy path sin incidencias

3. **Fallback de `load_state()`**
   - conserva `session_id` y `user_id` reales en corrupción
   - fallback `pending_session` solo cuando no hay identidad disponible

4. **`ensure_openai_thread()`**
   - conserva modo estable de estado válido
   - bootstrap conversación cuando corresponde

5. **`shared_types.py`**
   - sin duplicados
   - sin superficie legacy eliminada

6. **E2E mínimo**
   - happy path
   - fallback sin cliente
   - parse error path
   - refusal path
   - path con `previous_response_id`

## Regeneración de snapshots
Se eliminó y regeneró completamente:

- `docs/code_snapshot_current/`

El nuevo snapshot refleja el estado exacto actual post-corrección (sin arrastre de snapshots previos).

## Huecos reales pendientes
Sigue pendiente (ya marcado en código) la política final de selección/deduplicación de memoria episódica (`///` en `flow_config.py`).

No se introdujeron shims ni compatibilidad falsa para ocultarlo.

```
