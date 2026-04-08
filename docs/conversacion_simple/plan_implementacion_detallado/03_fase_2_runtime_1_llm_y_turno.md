# 03 · Fase 2 — Runtime 1-LLM y ejecución de turno

## 1) Alcance de la fase

### Hecho observado

`negociacion` ejecuta 4 nodos online en `backend/negociacion/orchestration/flow_config.py` (`memory`, `phase_classifier`, `planner`, `executor`).

### Propuesta

Implementar runtime independiente en `backend/conversacion_simple/orchestration/flow_config.py` con un solo nodo lógico `brain`.

### Decisión operativa

Fase 2 construye runtime completo de turno, pero **sin integrar aún superficies públicas** (eso es Fase 3).

---

## Cierres conservadores de Fase 2

1. No tocar `backend/negociacion/orchestration/turn_contract.py` en Fase 2.
2. Runtime y trazas de `conversacion_simple` se implementan en namespace propio.
3. Sin integración de superficies ni cambios en `backend/api/app.py`.

---

## 2) Qué se hará

1. Definir contrato `BrainInput` y `BrainOutput`.
2. Implementar builder de mensajes para llamada única LLM.
3. Implementar parseo/validación estricta de `BrainOutput`.
4. Implementar `apply_brain_output_to_state(...)` determinista.
5. Reusar guardrails input/output.
6. Persistir estado + recent dialogue + trace single-node.
7. Exponer función principal:
   - `run_conversacion_simple_turn(state, user_message, config, validated_context=...)`.

---

## 3) Archivos nuevos a crear (propuestos)

## 3.1 Nodos y contratos

- `backend/conversacion_simple/nodes/__init__.py`
- `backend/conversacion_simple/nodes/brain_node.py`

## 3.2 Orquestación runtime

- `backend/conversacion_simple/orchestration/flow_config.py` *(completa en esta fase)*
- `backend/conversacion_simple/orchestration/pipeline.py`
- `backend/conversacion_simple/orchestration/run_contract.py` *(si se separa helper específico)*

## 3.3 Traces

- `backend/conversacion_simple/traces/__init__.py`
- `backend/conversacion_simple/traces/models.py`
- `backend/conversacion_simple/traces/builders.py`

## 3.4 Tests

- `backend/tests/test_conversacion_simple_run_turn_context_guard.py`
- `backend/tests/test_conversacion_simple_brain_output_contract.py`
- `backend/tests/test_conversacion_simple_single_llm_path.py`
- `backend/tests/test_conversacion_simple_state_patch_determinism.py`
- `backend/tests/test_conversacion_simple_trace_contract.py`

---

## 4) Archivos existentes a modificar (propuestos)

1. `backend/negociacion/orchestration/turn_contract.py`
   - **Solo si necesario** para hacerlo flow-agnostic con bajo riesgo.
   - Alternativa preferida: copiar patrón en `conversacion_simple` y no tocar este archivo en Fase 2.
2. `backend/negociacion/orchestration/context_errors.py`
   - opcional, si se reusa tal cual sin duplicar errores.

> Decisión preferida de bajo riesgo: no tocar estos archivos en Fase 2; duplicar patrón en namespace `conversacion_simple`.

---

## 5) Funciones/clases concretas propuestas

## Contratos

- `class BrainTaskContract(BaseModel)`
- `class BrainInput(BaseModel)`
- `class BrainOutput(BaseModel)`
- `class BrainAssistantResponse(BaseModel)`
- `class BrainStatePatch(BaseModel)`

## Runtime

- `build_brain_input(canonical_state, recent_dialogue, user_turn, trace_meta, prompts_dir)`
- `build_brain_messages(brain_prompt, payload)`
- `_call_brain_structured(...)`
- `_resolve_brain_call_result(...)`
- `apply_brain_output_to_state(canonical_state, brain_output)`
- `run_conversacion_simple_turn(...)`
- `build_conversacion_simple_pipeline_config(...)`

## Persistencia

- `class ConversationSimpleStateRepository`
  - `load_state`
  - `save_state`
  - `load_recent_dialogue`
  - `save_recent_dialogue`
  - `append_trace`

## Trace

- `build_brain_node_trace(...)`
- `ConversationSimpleTurnTrace`

---

## 6) Lógica reutilizada vs lógica replicada

## Reutilizar directamente

1. Guardrails:
   - `backend/negociacion/guards/*`
2. Utilidades de sesión:
   - `sessions.state`, `sessions.lifecycle`, `sessions.session_lock`
3. Patrón de validación contextual:
   - estructura conceptual de `validate_turn_context_pre_execution`.

## Replicar/adaptar

1. Runtime orchestration de `flow_config.py` (evitar tocar monolito existente).
2. builders de trace con shape single-node.
3. modelos de input/output de nodo.

## NO tocar

- nodos `memory/phase_classifier/planner/executor` de `negociacion`.
- pipeline actual de `negociacion`.

---

## 7) Garantía de “1 sola llamada LLM en camino crítico”

### En código

- `run_conversacion_simple_turn` tendrá exactamente una invocación a `_call_brain_structured`.
- No habrá llamadas a nodos secundarios en esa ruta.
- Validar por test con spy/mock del cliente OpenAI.

### En trazas

- `stage_timings_ms` solo incluirá etapa `brain_call` como llamada de modelo principal.
- `nodes` contendrá `brain` (y nunca `memory/phase/planner/executor` en ese flow).
- Campo explícito recomendado: `pipeline_topology = "single_llm"`.

---

## 8) Qué desaparece del online y qué absorbe el nuevo runtime

## Desaparece del online

- memory call separada
- phase classifier call separada
- planner call separada
- executor call separada

## Absorbe `brain`

- decisión táctica,
- formulación de respuesta final,
- patch de estado (fase/goal/conversation state),
- actualización de memoria operativa mínima (working + episodic_append).

---

## 9) Tests concretos de Fase 2

1. `test_single_llm_call_per_turn`.
2. `test_brain_output_rejected_on_invalid_schema`.
3. `test_state_patch_applied_deterministically`.
4. `test_guardrails_can_rewrite_or_block_brain_output`.
5. `test_trace_contains_brain_node_and_topology_single_llm`.
6. `test_recent_dialogue_updated_and_trimmed`.
7. `test_context_precheck_blocks_mismatch`.

---

## 10) Riesgos de Fase 2

1. Sobrepeso del contrato `BrainOutput`.
2. Pérdida de granularidad de observabilidad al colapsar nodos.
3. Accidentes de compatibilidad con tooling de traces.

### Mitigación

- schema estricto + tests de contrato.
- trazas ricas de `brain_input_summary` y `state_patch_summary`.
- mantener envelope de trace compatible.

---

## 11) Criterio de Done de Fase 2

- Runtime de turno funciona en pruebas unitarias/integración aislada.
- Evidencia de una única llamada LLM por turno.
- State patch determinista y validado.
- Trace single-node estable y consumible.
- Ninguna regresión en tests de `negociacion` relevantes.
