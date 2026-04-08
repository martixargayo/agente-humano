# 06 · Mapa transversal de archivos y funciones

> Inventario operativo para ejecutar el plan por fases.

## 1) Archivos nuevos propuestos por fase

## Fase 1

- `backend/conversacion_simple/__init__.py`
- `backend/conversacion_simple/contexts/{__init__.py,models.py,resolver.py,session_binding.py,public_mapping.py}`
- `backend/conversacion_simple/state/{__init__.py,shared_types.py,canonical_state.py}`
- `backend/conversacion_simple/orchestration/{__init__.py,flow_config.py}` *(sólo config base)*
- `backend/conversacion_simple/services/{__init__.py,turn_context_factory.py}`
- `backend/conversacion_simple/contexts/baseline/**`
- `backend/conversacion_simple/contexts/negociacion_sala_reuniones/**`
- tests Fase 1 (`test_conversacion_simple_context_*`, `assets_schema`, `canonical_state_defaults`)

## Fase 2

- `backend/conversacion_simple/nodes/{__init__.py,brain_node.py}`
- `backend/conversacion_simple/orchestration/pipeline.py`
- `backend/conversacion_simple/traces/{__init__.py,models.py,builders.py}`
- tests Fase 2 (`single_llm_path`, `brain_output_contract`, `state_patch_determinism`, `trace_contract`)

## Fase 3

- `backend/conversacion_simple/services/{session_service.py,turn_service.py}`
- tests E2E/superficies Fase 3

## Fase 4

- `backend/conversacion_simple/memory/{__init__.py,policy.py,compression.py,fallback.py,maintenance.py}`
- tests de compresión/memoria larga Fase 4


## Decisiones cerradas de alcance Fase 1

1. **prompt_io_mapping:** en Fase 1 no se duplica motor; se reutiliza/reexporta el existente sin activación nueva específica del runtime.
2. **turn_contract compartido:** en Fase 1 no se toca `backend/negociacion/orchestration/turn_contract.py`.
3. **context errors:** taxonomía propia en namespace `conversacion_simple` sin modificar errores operativos de `negociacion`.
4. **presentation:** no hay capa de presentation propia integrada en Fase 1; solo estructura de assets de contexto.
5. **naming congelado:** se congela naming base: `backend/conversacion_simple/`, `ConversationSimpleCanonicalState`, `build_default_conversation_simple_canonical_state`, `build_conversacion_simple_turn_context`, `ConversationSimpleTurnConfig`, `conversation_simple_canonical`, `conversation_simple_canonical_recent_dialogue`, `conversation_simple_canonical_traces`.

---

## 2) Archivos existentes a modificar por fase

## Fase 1

- `docs/conversacion_simple/*` (documentación de soporte)
- `backend/README.md` *(opcional inventario de flow)*

## Fase 2

- Preferencia: **no tocar** archivos de `negociacion`.
- Opcional mínima: reuso explícito de utilidades comunes (sin cambiar comportamiento).

## Fase 3

- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario/models.py` *(si añade metadato flow-aware)*
- `backend/interfaz_usuario/presentation_resolver.py` *(si requiere resolver multi-flow)*
- `backend/negociacion/optimizador/services.py`
- `backend/negociacion/optimizador/trace_reader.py`
- `backend/negociacion/optimizador/context_bridge.py`
- `backend/api/app.py` *(si rutas/serving requieren ajuste flow-aware)*

## Fase 4

- `backend/conversacion_simple/orchestration/flow_config.py`
- `backend/conversacion_simple/state/canonical_state.py`
- `backend/conversacion_simple/traces/models.py`
- `backend/conversacion_simple/traces/builders.py`

---

## 3) Detalle por archivo (por qué / fase / tipo de cambio)

### `backend/interfaz_usuario/services.py`

- **Fase:** 3
- **Por qué:** enrutar runtime por flow/context sin romper endpoints.
- **Cambio:** aditivo + pequeñas ramas flow-aware.
- **Riesgo:** regresión en flujo `negociacion`.
- **Mitigación:** tests de no regresión IU existentes + nuevos de `conversacion_simple`.

### `backend/negociacion/optimizador/trace_reader.py`

- **Fase:** 3
- **Por qué:** soportar nodos single-node en traces.
- **Cambio:** comportamiento extendido.
- **Riesgo:** comparadores viejos asumían 4 nodos.
- **Mitigación:** tests mixed-flow.

### `backend/conversacion_simple/orchestration/flow_config.py`

- **Fases:** 1, 2, 4
- **Por qué:** núcleo de config/runtime/memoria del nuevo flow.
- **Cambio:** aditivo (archivo nuevo, evolución por fases).
- **Riesgo:** crecimiento monolítico.
- **Mitigación:** separar helpers por módulos (`nodes`, `memory`, `traces`).

---

## 4) Funciones/clases nuevas propuestas (inventario completo)

## Fase 1

1. `resolve_conversacion_simple_context(...)`
2. `resolve_default_conversacion_simple_context()`
3. `list_official_conversacion_simple_contexts()`
4. `ensure_conversacion_simple_session_context(...)`
5. `read_bound_conversacion_simple_context_from_session(...)`
6. `ConversationSimpleCanonicalState`
7. `build_default_conversation_simple_canonical_state(...)`
8. `build_conversacion_simple_turn_context(...)`
9. `ConversationSimpleTurnConfig`
10. `build_conversacion_simple_pipeline_config(...)` *(base)*

## Fase 2

1. `BrainInput`
2. `BrainOutput`
3. `build_brain_input(...)`
4. `build_brain_messages(...)`
5. `_call_brain_structured(...)`
6. `apply_brain_output_to_state(...)`
7. `run_conversacion_simple_turn(...)`
8. `ConversationSimpleStateRepository`
9. `ConversationSimpleTurnTrace`
10. `build_brain_node_trace(...)`

## Fase 3

1. `ensure_session_conversacion_simple(...)` *(service)*
2. `run_conversacion_simple_turn_service(...)`
3. `resolve_flow_for_context(...)` *(adaptador flow-aware en superficies)*

## Fase 4

1. `should_schedule_memory_compaction(...)`
2. `schedule_memory_compaction(...)`
3. `run_memory_compaction_deferred(...)`
4. `build_deterministic_compaction_fallback(...)`
5. `apply_compaction_result(...)`
6. `record_memory_maintenance_trace(...)`

---

## 5) Funciones/clases existentes que se tocarán (si aplica)

1. `interfaz_usuario.services.ensure_session` / `run_turn`
   - **Tipo:** agregar routing flow-aware.
   - **Riesgo:** romper invariantes en `negociacion`.
   - **Mitigación:** tests regressión + contract tests.
2. `optimizador.services.run_sandbox_turn`
   - **Tipo:** routing flow-aware + metadata de topology.
   - **Riesgo:** compare tooling inconsistente.
   - **Mitigación:** tests compare mixed-flow.
3. `optimizador.trace_reader.*`
   - **Tipo:** extender parser de nodes.
   - **Riesgo:** assumptions de 4 nodos.
   - **Mitigación:** fixtures de trace brain-only.

---

## 6) Relación con equivalentes en `negociacion`

- `resolve_conversacion_simple_context` ↔ `resolve_negotiation_context`
- `ConversationSimpleCanonicalState` ↔ `CanonicalState`
- `run_conversacion_simple_turn` ↔ `run_negotiation_cognitive_turn`
- `build_brain_input` ↔ combinación de `build_memory_input/build_phase_input/build_planner_input/build_executor_input`
- `build_brain_node_trace` ↔ `build_*_node_trace` existentes

---

## 7) Nota de control de alcance

Este mapa **no autoriza implementación directa**; define exactamente qué piezas deberán aparecer por fase y dónde.


## Actualización de cierre para Fase 2 implementada

- `turn_contract.py` de `negociacion` permanece sin cambios en Fase 2.
- `pipeline`/`nodes`/`traces` de `conversacion_simple` viven en namespace propio.
- Integraciones de superficies quedan explícitamente para Fase 3.
