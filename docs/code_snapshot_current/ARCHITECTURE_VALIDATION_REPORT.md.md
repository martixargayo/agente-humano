# File Snapshot

Original path:
`backend/negociacion/ARCHITECTURE_VALIDATION_REPORT.md`

Snapshot status:
`current`

Language / type:
`markdown`

```markdown
# Architecture Validation Report

## 1) Archivos eliminados
Se eliminaron completamente estos artefactos provisionales/viejos:

- `backend/tests/fixtures/negotiation/canonical_state_minimal.json`
- `backend/tests/fixtures/negotiation/executor_output_valid.json`
- `backend/tests/fixtures/negotiation/memory_output_valid.json`
- `backend/tests/fixtures/negotiation/phase_classifier_output_valid.json`
- `backend/tests/fixtures/negotiation/planner_output_valid.json`
- `backend/tests/fixtures/negotiation/turn_trace_golden.json`
- `backend/tests/test_negotiation_architecture_validation.py`
- `backend/tests/test_negotiation_cognitive_architecture.py`
- `backend/negociacion/TEST_EVIDENCE.md`
- `backend/negociacion/TEST_PLAN.md`

No se crearon copias `_old`, `_bak` ni equivalentes.

## 2) Tests nuevos
Se creó una suite única de validación en:

- `backend/tests/test_negotiation_architecture_clean.py`

La suite reemplaza fixtures JSON externos por datos en línea en Python para que la validación sea directa y trazable.

## 3) Wiring probado explícitamente
La suite cubre wiring real del pipeline y nodos:

- Estado canónico -> `build_memory_input`, `build_phase_input`, `build_planner_input`, `build_executor_input`.
- `persona.policy` presente en `PlannerInput`.
- `persona.expressive` presente en `ExecutorInput`.
- `planner_state.current_phase` usado para seleccionar/inyectar `phase_card` en planner y executor.
- `PlannerOutput.limits` traducido a `ExecutorInput.response_limits`.
- `MemoryOutput` aplicado sobre `memory_episodic` + `memory_working`.
- `PhaseClassifierOutput` aplicado sobre `previous_phase` + `current_phase`.
- Mensajes de nodos (`developer` estable, `user` dinámico serializado) para:
  - memory
  - phase classifier
  - planner
  - executor
- Convención de diálogo runtime confirmada en `role + text`.

## 4) Invariantes del estado canónico demostrados
Se valida explícitamente que:

- `CanonicalState.model_fields.keys()` contiene exactamente 8 grupos.
- `model_dump(mode="json")` contiene exactamente esos 8 grupos.
- No existen atributos legacy en `CanonicalState`:
  - `recent_messages`
  - `session_settings`
  - `memory_profile`
  - `relationship`
  - `safety`
  - `voice`
  - `plan`

## 5) Contratos nuevos verificados
La suite verifica uso real y shape de contratos:

- Memory: `MemoryInput`, `MemoryOutput`, `MemoryEpisode`, `MemoryWorking`.
- Phase classifier: `PhaseClassifierInput`, `PhaseClassifierOutput`.
- Planner: `PlannerInput`, `PlannerOutput`.
- Executor: `ExecutorInput`, `ExecutorOutput`.

Y anti-legacy checks:

- `PlannerOutput` sin `style_band`, `conversation_act`, `current_phase`, `policy`, `safety`, `situation`.
- `ExecutorOutput` sin `tts`, `conversation_act_realized`.
- ausencia de nombres legacy de memory (`MemoryPatch`, `profile_updates`, `relationship_updates`, `safety_updates`).

## 6) Dependencias legacy confirmadas eliminadas
Se valida que:

- Builders no referencian `canonical_state.recent_messages`, `canonical_state.session_settings`, `canonical_state.plan` ni otros attrs legacy.
- El runtime puede correr el turno completo con un estado canónico mínimo sin depender de keys legacy en `world_state`.
- `shared_types.py` no tiene clases enum duplicadas (chequeo de unicidad por AST).

## 7) Huecos reales pendientes
Pendiente real detectado y mantenido explícito en código:

- Política final de selección/deduplicación de memoria sigue marcada como provisional (`///`) en `flow_config.py`.

No se ocultó con tests ni con shims.

## 8) Evidencia de ausencia de rastro viejo relevante
La evidencia se basa en:

- tests de contratos (reject de campos extra/legacy por `extra="forbid"`),
- tests de wiring de builders y aplicación de outputs,
- tests e2e de turno completo con cliente fake:
  - clima humano,
  - descubrimiento,
  - concesión/oferta,
  - fallback sin cliente,
  - parse error en planner,
  - refusal en executor,
- tests de inspección de source (AST) para confirmar que no hay dependencia directa de atributos legacy del canónico.

```
