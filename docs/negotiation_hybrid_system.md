# Sistema de negociación híbrido (hybrid pipeline)

## 1) Visión general

El sistema de negociación está diseñado para convertir una conversación libre con un vendedor en una respuesta estratégica, consistente con reglas de negocio (límite de coste, no revelar cifras propias, etc.). Lo hace combinando:

- **Extracción de estado del mundo** (hechos del vendedor, evidencias, señales de tono).
- **Actualización de creencias** (postura y salud de la interacción).
- **Gestión de intención** (pasos y slots a completar).
- **Planificación de fase + policy** (selección estratégica del micro-objetivo y riesgo).
- **Ejecución** (redacción de la respuesta final) con **validación y reparación**.

A esto se le llama **“hybrid pipeline”** porque combina reglas deterministas y compuertas (“gates”) con modelos LLM que generan estructuras JSON. El flujo “híbrido” se ve en:

- **World/BELIEF/Phase+Policy/Executor** con **gates** para saltar llamadas costosas.
- **Validator override** que puede reescribir la respuesta si viola guardrails.

**Source-of-truth de policy**: 
- **policy_chosen** = `policy_decision` (decisión generada por el planner).
- **policy_executed** = `executed_policy` (decisión efectiva, que puede ser sobrescrita por el validador si detecta violaciones). Estas dos pueden diferir cuando `validate_and_repair` devuelve `override_policy_id`.

## 2) Flujo de un turno (paso a paso)

### 2.1 run_negotiation_agent (entrada/salida del sistema)

**Entrada principal**: `SessionState`, `user_message`, y `deps` (inyección de dependencias). 

**Pasos clave**:

1. **Persistencia de mensajes**: se añade el mensaje del vendedor al historial.
2. **Contexto + memoria**: se actualiza/recorta resumen, se generan bloques de memoria y contexto reciente.
3. **Constraints y límites**: se deriva `max_total_cost` y `constraints_struct` desde la opción de salida.
4. **Normalización**: se normalizan `world_state`, `belief_state`, `progress_state` y `last_policy_executed`.
5. **Construcción de `graph_state`**: prepara el estado completo para LangGraph.
6. **Ejecución del grafo**: `negotiation_app.invoke(graph_state)` procesa los nodos.
7. **Persistencia**: actualiza `SessionState`, añade la respuesta y agrega un `debug_trace` por turno.

### 2.2 Nodos del grafo (orden real)

#### (1) `world_updater_node`
- **Lee**: `progress_state.gate_state`, `user_message`, `turn_count`, `prev_world_state`.
- **Escribe**: `world_state`, `world_diff`, `prev_world_state`, `extractor_meta`, `progress_state.gate_state`.
- **Meta**: `extractor_meta` incluye si se saltó el extractor, `skip_reason`, y `world_gate_features`.
- **Gating**: usa `gate_world` con `input_shape_features` + intervalo; si expira el intervalo fuerza `force_llm`.

#### (2) `belief_updater_node`
- **Lee**: `world_state`, `world_diff`, `prev_belief_state`, `last_policy_executed`, `last_assistant_message`.
- **Escribe**: `belief_state`, `belief_update_meta`, `progress_state.gate_state`.
- **Meta**: `belief_update_meta` indica si se saltó el update y por qué.
- **Gating**: usa `gate_belief` (world_diff/flags/interval).

#### (3) `precedence_node`
- **Lee**: `world_state`, `belief_state`, `intent_state`.
- **Escribe**: `precedence` (modo, tags mínimos, bloqueo, fase mínima), `precedence_signature`.
- **Meta**: firma usada para gates posteriores.

#### (4) `intent_manager_node`
- **Lee**: `progress_state.intent_state`, `world_state`, `belief_state`, `precedence`, `user_message`.
- **Escribe**: `progress_state.intent_state`, `intent_hint`, `intent_meta`.
- **Meta**: `intent_meta` informa transiciones (pause/success/pivot) y razones.

#### (5) `phase_policy_planner_node`
- **Lee**: `world_state`, `world_diff`, `belief_state`, `progress_state`, `intent_hint`, `precedence`, `constraints`.
- **Escribe**:
  - `phase_candidate` + `phase_effective`
  - `policy_decision`, `policy_pre_repair`, `policy_post_repair`
  - `planner_meta`, `phase_meta`, `allowed_policy_ids`, `gate_meta`
  - actualiza `progress_state.gate_state`
- **Meta**:
  - `planner_meta`: errores, fallback, allowed_ids, intent/precedence
  - `phase_meta`: reasons/threshold/hysteresis
  - `gate_meta`: contadores de skips y razones por nodo
- **Gating**: el skip/replan del planner se decide directamente en `phase_policy_planner_node` (sin wrapper `gate_phase_policy`).
- **Reparación**: `repair_policy_by_phase` asegura compatibilidad con fase/intención.

#### (6) `progress_updater_node`
- **Lee**: `policy_decision`, `last_policy_executed`, `prev_world_state`, `world_state`, `prev_belief_state`, `belief_state`.
- **Escribe**: `progress_state` actualizado con intentos, outcomes y loop_flags.

#### (7) `executor_node`
- **Lee**: memoria, resumen, `policy_decision`, `phase_state`, `precedence`, `intent_hint`, `constraints_struct`.
- **Escribe**: `response`, `executed_policy`, `executor_validator_meta`, `override_policy_id`, `override_reason`.
- **Meta**: `executor_validator_meta` incluye `override_policy_id` cuando el validador fuerza un policy diferente.
- **Validator override**: `validate_and_repair` reescribe la respuesta si viola guardrails y puede forzar una policy segura.

#### (8) `validate_and_repair` (dentro del executor)
- **Lee**: `response_text`, `constraints_struct`, `policy_decision`, `world_state`.
- **Escribe**: `repaired_response`, `violations`, `override_policy_id`/`override_reason` si hay fallback.

## 3) Estados y schemas

Estados principales (ver `schemas.py`):

- **WorldState**: hechos del vendedor y señales (precio, urgencia, tono, evidencias). Incluye `world_observations_v2` y `world_state_meta`.
- **BeliefState**: `stance` (deal_feasibility, seller_flexibility), `dynamics` (interaction_health), `tom` (teoría de la mente) y `reasons`.
- **ProgressState**: tracking de `policy_attempts`, `policy_last_outcome`, `loop_flags`, `intent_state`, `phase_state` y `gate_state`.
- **GateState**: `last_world_refresh_turn`, `last_belief_refresh_turn`, `last_planner_refresh_turn`, contadores de skip y firmas de hash (`allowed_ids_hash_prev`, `precedence_signature_prev`).
- **PhaseState**: `phase`, `confidence`, `reasons`, `last_updated_turn`.
- **PolicyDecision**: `policy_id`, `reason`, `micro_goal`, `risk_posture`, `why_short`, `inputs_used`.

Campos críticos a observar:
- `world_diff` (cambios que alimentan gating y diagnosis).
- `loop_flags` y `turns_in_same_mode` (detectar loops en una policy).
- `allowed_ids_hash_prev`, `precedence_signature_prev` en `GateState` (estabilidad de planner).

Invariantes/clamps:
- Normalizaciones aseguran valores en rango (`confidence` ∈ [0,1], `tone_signal` permitido, listas deduplicadas).
- `normalize_*` rellena defaults cuando faltan campos y recorta arrays con límites máximos.

## 4) Gating y rendimiento

**Reglas de gate**

- **gate_world**: refresca si cambia la “shape” del input o si expira el intervalo.
- **gate_belief**: refresca si hay cambios críticos del mundo, cambio de tono o expiración.
- **Planner skip/replan**: se determina por `planner_request`, `advance_step`, `judgement_skip_planner` y estado del plan activo en `phase_policy_planner_node`.

**Barato vs caro**

- **Caro**: extractores LLM (`update_world_state` cuando force_llm), planner fase/policy con JSON estructurado, validador reparador.
- **Barato**: filtros deterministas (`allowed_policy_ids`, `apply_precedence_constraints`, `apply_intent_constraints`, `repair_policy_by_phase`), gates y diffs.

**Variables de entorno relevantes**

- Intervalos: `WORLD_REFRESH_INTERVAL_TURNS`, `BELIEF_REFRESH_INTERVAL_TURNS`, `PHASE_POLICY_REFRESH_INTERVAL_TURNS`.
- Extractores: `USE_LLM_EXTRACTOR`, `USE_LEGACY_MATCHERS`, `EVIDENCE_CONFIDENCE_MIN`, `EVIDENCE_V2_MAX_CLAIMS`, `EVIDENCE_V2_MAX_UNKNOWN`, `EVIDENCE_V2_RECENT_K`.
- Planner/Executor: `PHASE_POLICY_MODEL_NAME`, `PHASE_POLICY_TEMPERATURE`, `EXECUTOR_MODEL_NAME`/`OPENAI_MODEL_NAME`, `EXECUTOR_TEMPERATURE`.
- Resumen/memoria: `SUMMARY_MODEL_NAME`, `SUMMARY_TEMPERATURE`.
- Guardrails: `RESPONSE_VALIDATOR_MODEL`, `MAX_TOTAL_COST_MARGIN`, `STRICT_NORMALIZATION`.
- Intent manager: `INTENT_*` (umbrales de utilidades, decays, intent max turns).

## 5) Auditabilidad / debug_trace

Por turno se emite un `debug_trace` con:

- Estado world/belief antes/después + `world_diff`.
- `policy_decision`, `policy_pre_repair` y `policy_post_repair`.
- `phase_candidate` y `phase_effective`.
- `executed_policy` y cualquier override (`override_policy_id`, `override_reason`).
- `planner_meta`, `phase_meta`, `belief_update_meta`, `extractor_meta`, `gate_meta`.
- Estado de intent (transiciones, slots, commitment) y `progress_state` completo.
- Evidencias resumidas (`top_evidence_v2`) y contadores (`unknown_claims_count`).
- Resultados de normalización (`validation_issues`) + `memory_meta`/`refresh_meta`.

Los repairs pueden verse comparando `policy_pre_repair` vs `policy_post_repair`, y cualquier override del validator con `override_policy_id`.

## 6) Cómo correr / testear

- Tests rápidos: `pytest -q`.
- Script de demo de intent: `python backend/scripts/validate_intent_demo.py` (usa dependencias fake y genera un trace por turno).
