# Runtime blockers: wiring + parsing + schemas (estado actual)

> Alcance: inventario técnico del runtime **tal como está hoy** para entender por qué el sistema nuevo (`judge_semantic_v1` / `planner_semantic_v1` / executor semántico) rompe o queda degradado si solo se cambian prompts.
> 
> **No contiene propuestas de solución** ni cambios de código.

---

## 0) Resumen ejecutivo

Bloqueadores reales (runtime, no solo prompt):

1. **WORLD_JUDGE acoplado a schema legacy v1 + normalizers/evidence guardrails**.
   - El camino de judge parsea JSON libre y luego lo normaliza forzando `plan_status`, `evidence`, `missing_signals`, `skip_planner`, además de reglas de degradación (`missing_evidence_for_progress`, forced replan por `same_step_no_progress_turns`).
   - Aunque el LLM devolviera un schema nuevo, el runtime lo reconduce al contrato v1 o a fallback v1.

2. **PLANNER acoplado a `PlannerV2DecisionModel` con `with_structured_output` + shape `planner_v2`**.
   - El planner exige validación Pydantic estricta de campos legacy (`schema_version`, `phase`, `recovery_mode`, `policy_id`, `active_plan`, `executor_instruction`).
   - Si el LLM devuelve `planner_semantic_v1` (sin `policy_id/active_plan/executor_instruction`), se activa excepción/parse failure y fallback de plan legacy.

3. **EXECUTOR acoplado a `executor_instruction_json` + lógica de “step ask/final question” + contratos de max_questions/slots**.
   - El pipeline construye prompt del executor desde `strategy_summary.executor_instruction` y resume `plan_id/policy_id`.
   - Postprocesos (`_enforce_executor_v2_contract`, `_instruction_followed`, `_enforce_executor_instruction`) mantienen expectativas de pregunta, slots y cumplimiento de instrucción de step.

---

## 1) Call graph real (runtime) y contratos por tramo

Diagrama textual solicitado y contraste con orden efectivo:

- Cadena funcional (con judge dentro de world):
  `world_updater_node -> world_judge_llm -> policy_progress_node -> phase_policy_planner_node -> executor_node -> progress_updater_node`
- Orden efectivo en `negotiation_graph.py` (edges):
  `world_updater -> belief_updater -> policy_progress -> phase_policy_planner -> progress_updater -> executor`

(En `world_updater_node` se ejecuta internamente `world_judge_llm` y se persiste `state["policy_plan_judgement"]`.)

### 1.1 `world_updater_node` → `world_judge_llm`

- **(a) Función + archivo**
  - `world_updater_node`, `world_judge_llm` en `backend/negotiation/nodes/world_node.py`.
- **(b) Input principal**
  - `active_plan`, `current_step`, `success_criteria`, `user_message`, `assistant_last_message`, `recent_history`, `progress_counters`, `evidence_candidates`, world digest/full, memoria.
- **(c) Output principal**
  - `judgement` normalizado v1 en `state["policy_plan_judgement"]`.
- **(d) Quién consume después**
  - `policy_progress_node` (status/planner_request), `planner_node` (gates skip/replan), `progress_updater` (ledger/counters).
- **(e) Hard requirements hoy**
  - `plan_status` v1 + `evidence` + `skip_planner` + `missing_signals` son usados por lógica posterior.

### 1.2 `policy_progress_node`

- **(a) Función + archivo**
  - `policy_progress_node` en `backend/negotiation/nodes/policy_progress_node.py`.
  - `update_policy_state` en `backend/negotiation/policy_progress.py`.
- **(b) Input principal**
  - `policy_plan_judgement.plan_status`.
- **(c) Output principal**
  - `progress_state.policy_state.planner_request` (`continue_policy` / `replan_policy`).
  - `progress_state.advance_step`.
- **(d) Quién consume después**
  - `phase_policy_planner_node`.
- **(e) Hard requirements hoy**
  - `_ALLOWED_STATUS = {continue_same_step, advance_step, completed, interrupted_replan}`.

### 1.3 `phase_policy_planner_node` → `plan_phase_policy`

- **(a) Función + archivo**
  - `phase_policy_planner_node` en `backend/negotiation/nodes/planner_node.py`.
  - `plan_phase_policy` en `backend/negotiation/phase_policy_planner.py`.
- **(b) Input principal**
  - `policy_state.planner_request`, `policy_plan_judgement`, `progress_state.active_plan`, `plan_ledger`, `progress_counters`, allowed policies, advisor/judge payloads.
- **(c) Output principal**
  - `policy_decision`, `phase_candidate`, `meta.active_plan`, `meta.executor_instruction`, `state["executor_instruction"]`.
- **(d) Quién consume después**
  - `progress_updater_node` y `executor_node`.
- **(e) Hard requirements hoy**
  - Structured output contra `PlannerV2DecisionModel` y presencia de `active_plan`/`executor_instruction`.

### 1.4 `progress_updater_node`

- **(a) Función + archivo**
  - `progress_updater_node` en `backend/negotiation/nodes/progress_node.py`.
  - `update_progress_state` en `backend/negotiation/progress_updater.py`.
- **(b) Input principal**
  - `policy_plan_judgement`, `active_plan`, `executor_output`, `advisor_signals`.
- **(c) Output principal**
  - `progress_state` con counters, `plan_ledger`, flags, plan churn, etc.
- **(d) Quién consume después**
  - `executor_node` en el mismo turno y nodos en turnos siguientes.
- **(e) Hard requirements hoy**
  - Campos legacy: `same_step_no_progress_turns`, `plan_id_changes_window`, `loop_flags`, `plan_ledger.*`.

### 1.5 `executor_node` → render

- **(a) Función + archivo**
  - `executor_node` en `backend/negotiation/nodes/executor_node.py`.
  - `render_executor_output` en `backend/negotiation/executor/render_executor.py`.
- **(b) Input principal**
  - `strategy_summary.executor_instruction`, `advisor_recs`, world/belief, memory, planner summary.
- **(c) Output principal**
  - `executor_output` (`executor_v2`), `assistant_message`.
- **(d) Quién consume después**
  - `progress_updater` en siguiente turno (asked question ledger), observabilidad y validadores.
- **(e) Hard requirements hoy**
  - Prompt espera `executor_instruction_json`; post-validación usa límites de preguntas/slots y compliance de instrucción.

---

## 2) WORLD_JUDGE: wiring + parsing + normalizers (bloqueador #1)

Archivos principales:
- `backend/prompts.py`
- `backend/negotiation/nodes/world_node.py`

Funciones/zonas clave:
- `world_judge_llm`
- `_normalize_judgement`
- `_post_normalize_evidence_guardrails`
- `_build_evidence_candidates`
- `_fallback_judgement` (fallback v1)

### 2.A JSON exacto que espera parsear hoy (contract legacy)

Prompt v2 exige schema v1 con:
- `schema_version: "v1"`
- `turn_idx`
- `plan_presence`
- `plan_id`
- `evaluated_step_idx`
- `plan_status: continue_same_step|advance_step|completed|interrupted_replan`
- `why`
- `evidence: [{quote, source, span}]`
- `confidence`
- `missing_signals`
- `safety_flags`
- `degraded`
- `degrade_reason`
- `skip_planner`

### 2.B Qué pasa si llega `schema_version` distinto o faltan `plan_status/evidence`

- No hay chequeo estricto de `schema_version`; `_normalize_judgement` toma defaults legacy.
- Si falta `plan_status`, cae a `continue_same_step`.
- Si status es `advance_step/completed` sin evidence, lo degrada a `continue_same_step` con `degrade_reason="missing_evidence_for_progress"`.
- Si `same_step_no_progress_turns >= 1` y status `continue_same_step`, fuerza `interrupted_replan`.
- Si parse/shape falla completo, `world_judge_llm` retorna `_fallback_judgement` legacy v1.

### 2.C Dónde se degrada/reescribe output del judge

- `_normalize_judgement`:
  - corrige status a set permitido.
  - fuerza downgrade por falta de evidence.
  - fuerza replan por contador de no progreso.
  - anula `skip_planner` si status != `continue_same_step`.
- `_post_normalize_evidence_guardrails`:
  - inyecta evidence si hay texto/missing signals.
  - marca `degraded` y `degrade_reason` por missing evidence.
  - limpia `missing_signals` según evidence.

### 2.D Qué campos del judge se usan aguas abajo

- `policy_progress.update_policy_state` consume `plan_status` para setear `planner_request`.
- `phase_policy_planner_node` consume:
  - `plan_status` (gate `judge_requires_change`),
  - `skip_planner` (skip gate),
  - `degraded` para debug/gating contextual.
- `progress_updater.update_progress_state` consume:
  - `plan_status`,
  - `evidence`,
  - `why/degrade_reason`,
  - `evaluated_step_idx`,
  para counters/ledger.

### 2.E Shape contract actual del judge (obligatorio por código)

**Obligatorios de facto por código (aunque no se valide con Pydantic aquí):**
- `plan_status` (si no, default legacy; sigue siendo requerido funcionalmente).
- `evidence` (guardrails inyectan o degradan).
- `skip_planner` (participa en gate de planner node).
- `evaluated_step_idx`, `plan_id`, `plan_presence` (usados para no-progress tracking).
- `why/degrade_reason/missing_signals` (telemetría + ledger/correcciones).

---

## 3) PLANNER: structured_output + schema planner_v2 (bloqueador #2)

Archivos principales:
- `backend/prompts.py`
- `backend/negotiation/phase_policy_planner.py`
- `backend/negotiation/nodes/planner_node.py`
- `backend/negotiation/elementos/strategy_definitions.py`

### 3.A Modelo Pydantic usado

- `PlannerV2DecisionModel` en `backend/negotiation/elementos/strategy_definitions.py`.
- Invocación: `llm.with_structured_output(PlannerV2DecisionModel)` en `plan_phase_policy`.

### 3.B Campos obligatorios planner_v2 hoy

`PlannerV2DecisionModel` requiere:
- `schema_version: "planner_v2"`
- `phase`
- `recovery_mode`
- `policy_id`
- `active_plan` (`PlannerV2ActivePlanModel`)
  - `plan_id`, `current_step_idx`, `context_digest`, `steps` (2..5)
  - cada step: `intent_id`, `instruction`, `ask_slots<=1`, `success_criteria`, etc.
- `executor_instruction` (`PlannerV2ExecutorInstructionModel`)
  - `plan_id`, `step_idx`, `instruction`, `ask_slots<=1`, `max_questions_per_turn<=1`, etc.

### 3.C Conversión payload → phase/policy/meta y uso de active_plan

En `plan_phase_policy`:
- `payload = result.model_dump()`.
- `phase_candidate` sale de `payload.phase/recovery_mode`.
- `policy_decision.policy_id` sale de `payload.policy_id`.
- `policy_decision.micro_goal` extrae `payload.active_plan.steps[0].goal`.
- `meta["active_plan"] = _to_active_plan(payload.active_plan, turn)`.
- `meta["executor_instruction"] = payload.executor_instruction`.

En `phase_policy_planner_node`:
- usa `meta.active_plan` para `progress_state.active_plan`.
- usa `meta.executor_instruction` para `state["executor_instruction"]` (si planner v2).
- gates y validaciones inspeccionan `active_plan.steps/current_step_idx` y ledger.

### 3.D Qué rompe si planner devuelve `planner_semantic_v1`

Si el LLM responde solo `{schema_version: planner_semantic_v1, phase, style, next_move_hint, ...}`:
- `with_structured_output(PlannerV2DecisionModel)` falla validación (faltan `policy_id`, `active_plan`, `executor_instruction`; schema_version mismatch).
- Ruta de excepción en `plan_phase_policy` marca `planner_failed`, activa `planner_fallback_used` y devuelve `_fallback_plan` + `_fallback_policy` legacy.
- Resultado: no rompe con excepción fatal siempre, pero **sí rompe el contrato nuevo** y vuelve a plan legacy automáticamente.

### 3.E Funciones que asumen `active_plan.steps/current_step_idx/success_criteria`

- `world_judge_llm` (extrae `current_step`, `success_criteria`).
- `planner_node._clamp_step`, `_advance_step`, `validate_active_plan_against_ledger`, `_build_executor_instruction`, `_plan_hits_blocked_topic`.
- `phase_policy_planner._to_active_plan` (normalización fuerte de steps).
- `progress_updater._extract_current_intent_id` / `_extract_judged_step_idx` / `_compute_same_step_no_progress_turns`.

### 3.F Shape contract actual planner_v2 (requerimientos reales)

Requerimiento real no es solo prompt: está en `with_structured_output + PlannerV2DecisionModel` (Pydantic con `extra="forbid"`).
- Campos fuera de schema o faltantes → excepción de parse/validation.
- Por eso pegar prompt nuevo sin tocar parsing/modelo conduce a fallback legacy.

---

## 4) EXECUTOR: dependencia de `executor_instruction_json` + step question (bloqueador #3)

Archivos principales:
- `backend/negotiation/elementos/render/executor_prompts.py`
- `backend/negotiation/executor/render_executor.py`
- `backend/negotiation/nodes/executor_node.py`

### 4.A Campos de `strategy_summary` que se pasan

En `render_executor_output` se interpola:
- `executor_instruction_json = strategy_summary.get("executor_instruction", {})`
- `planner_output_summary = {phase, policy_id, plan_id}`
- `retry_hint` derivado de `policy_plan_judgement.plan_status` + no-progress

### 4.B Dónde se fuerza max_questions / step-final-question / slots

- Prompt system (`EXECUTOR_V2_SYSTEM_PROMPT`) exige lógica human-first con “pregunta final del step”.
- `EXECUTOR_V2_OUTPUT_SCHEMA` impone `max_questions=1` y coherencia de slots si pregunta.
- `_enforce_executor_v2_contract`:
  - trunca por `style_contract.max_words`.
  - reduce preguntas por `style_contract.max_questions`.
  - si hay pregunta y no slots, autoasigna `detalle_verificable`; si no hay pregunta limpia slots.
- `_enforce_executor_instruction` en `executor_node` aplica:
  - `must_avoid` y `max_questions_per_turn` de `executor_instruction`.
- `_instruction_followed` verifica cumplimiento de `instruction/ask` del step (incluye caso `missing_question_for_instruction` y `missing_required_ask_slot`).

### 4.C Qué falla si no existe `executor_instruction_json` o llega vacío

- Render no siempre rompe (se serializa `{}`), pero se pierde el contrato operativo esperado por validaciones downstream.
- `_instruction_followed` retorna pass si `instruction` vacío, pero el resto de pipeline sigue acoplado a planner summary/step artifacts.
- El diseño actual asume pipeline plan-driven; salida semántica pura del planner no llega al executor por placeholders actuales.

### 4.D Shape contract real del output del executor y validación

Contrato esperado (`executor_v2`):
- `schema_version`, `response_text`, `asked_question`, `requested_info_slots`, `tone_used`, `followup_intent`, `render_meta`.

Validaciones/postproceso:
- `normalize_executor_output` (normaliza faltantes/tipos).
- `_enforce_executor_v2_contract` (preguntas, slots, style limits, sanitización).
- `validate_and_repair` en `executor_node`.
- `_enforce_executor_instruction` + `_instruction_followed`.

### 4.E Dónde se registra `asked_question/requested_info_slots` y consumo posterior

- `executor_node._register_recent_question` persiste pregunta en `progress_state.plan_ledger.asked_questions_recent`.
- `progress_updater._record_recent_question` también alimenta ledger de preguntas recientes.
- `planner_v2` usa ese ledger en reglas anti-repetición (prompt y validaciones de plan).

---

## 5) Schemas y estado: `progress_state` / `policy_state` / `plan_ledger` (bloqueador transversal)

Archivo principal:
- `backend/negotiation/schemas.py`

Campos legacy que existen y se leen hoy:

### 5.1 `progress_counters` / contadores equivalentes

> Nota: no hay un objeto único `progress_counters` persistido tal cual en schema; los contadores existen distribuidos en `progress_state` y se serializan al prompt del judge/planner.

- `same_step_no_progress_turns` / `no_progress_same_step_turns`
  - **Escribe**: `progress_updater._compute_same_step_no_progress_turns`.
  - **Lee**: `world_judge_llm` (forced replan), `planner_node` (gate force replan), prompts v2.
- `plan_id_changes_window`
  - **Escribe**: `progress_updater.update_progress_state`.
  - **Lee**: loop flags/debug y prompting planner/judge.
- `loop_flags`
  - **Escribe**: `progress_updater.update_progress_state`.
  - **Lee**: planner gating/debug, prompts y telemetría.

### 5.2 `plan_ledger`

- Estructura: `resolved_intents`, `open_intents`, `failed_intents`, `asked_questions_recent`, `attempt_counters`, `blocked_topics`.
- **Escribe**:
  - `progress_updater._update_plan_ledger`
  - `progress_updater._decay_and_apply_blocked_topics`
  - `executor_node._register_recent_question`
- **Lee**:
  - prompt planner v2 (`plan_ledger_json`, `blocked_topics_json`)
  - `planner_node.validate_active_plan_against_ledger`
  - `planner_node` blocked-topic guards

### 5.3 `active_plan + current_step_idx + success_criteria`

- **Escribe**:
  - `plan_phase_policy` (`meta.active_plan`), planner node lo persiste.
- **Lee**:
  - `world_judge_llm` (current step + success criteria)
  - `planner_node` helpers de clamp/advance/validation
  - `progress_updater` para intent tracking/no-progress

### 5.4 `planner_request`, `advance_step`, `skip_planner`

- `planner_request`:
  - **Escribe**: `policy_progress.update_policy_state`.
  - **Lee**: `planner_node` gate path.
- `advance_step`:
  - **Escribe**: `policy_progress`.
  - **Lee**: planner flow / progress debug.
- `skip_planner` (dentro de judgement):
  - **Escribe**: judge + normalizer.
  - **Lee**: `planner_node` (skip gate).

### 5.5 Cuáles son críticos para no romper runtime hoy

Críticos de compatibilidad operativa inmediata:
- `policy_plan_judgement.plan_status`
- `progress_state.policy_state.planner_request`
- `progress_state.active_plan` (con `steps/current_step_idx`)
- `state.executor_instruction` / `meta.executor_instruction`
- `progress_state.plan_ledger` (al menos estructura mínima)
- `same_step_no_progress_turns` (usado por gates)

---

## 6) “Si pegamos los prompts nuevos, qué rompe exactamente”

### 6.1 Judge nuevo (`judge_semantic_v1`) sin campos legacy

**Síntoma esperado**
- No necesariamente excepción fatal, pero normalización legacy reescribe el output:
  - default `plan_status=continue_same_step`
  - evidence inyectada/degradada
  - forced replan por contador
- Resultado final guardado en estado sigue siendo schema v1-like, no semantic ledger.

**Dónde ocurre**
- `world_node.world_judge_llm` + `_normalize_judgement` + `_post_normalize_evidence_guardrails`.

**Condición**
- JSON parseable pero sin `plan_status/evidence/skip_planner`.

### 6.2 Planner nuevo (`planner_semantic_v1`) sin `policy_id/active_plan/executor_instruction`

**Síntoma esperado**
- `ValidationError`/parse error de structured output.
- Fallback a `_fallback_plan` y `_fallback_policy`.

**Dónde ocurre**
- `phase_policy_planner.plan_phase_policy` en `structured.invoke(messages)` con `PlannerV2DecisionModel`.

**Condición**
- Payload no compatible con schema `planner_v2`.

### 6.3 Executor semántico sin `executor_instruction_json` legacy

**Síntoma esperado**
- Si no se adapta wiring, prompt builder puede fallar por placeholders faltantes (si se cambia template sin cambiar `.format`).
- Si llega `{}` no siempre rompe, pero enforcement/validator sigue orientado a contratos de step/ask.

**Dónde ocurre**
- `render_executor_output` (`EXECUTOR_USER_PROMPT.format(...)`).
- `executor_node._instruction_followed` / `_enforce_executor_instruction`.

**Condición**
- Desalineación entre placeholders nuevos y args existentes; o ausencia de instruction step en pipeline.

### 6.4 Efecto en policy/progress por desaparición de `plan_status`

**Síntoma esperado**
- Sin `plan_status` válido, `policy_progress` cae en default `interrupted_replan` o ramas no previstas.
- `planner_request` y `advance_step` se alteran, afectando toda la cadena.

**Dónde ocurre**
- `policy_progress.update_policy_state`.

### 6.5 Riesgo tests/contratos automatizados

- Múltiples tests en `backend/tests/` verifican explícitamente `plan_status`, `active_plan`, `executor_instruction`, `planner_request`, invariantes de planner_v2.
- Cambiar solo prompts rompería expectativas de estos tests aunque runtime haga fallback.

---

## 7) Mínimo para Milestone 1 (solo judge ledger + persistencia) — dependencias inevitables (sin solución)

> Esta sección enumera dependencias a tocar inevitablemente para que `judge_semantic_v1` no sea descartado por el runtime actual. No prescribe diseño.

### 7.1 Componentes inevitables por dependencia de parsing/consumo

- `backend/negotiation/nodes/world_node.py`
  - porque ahí se parsea y normaliza el judge actual (v1 legacy) y se persiste `policy_plan_judgement`.
- `backend/negotiation/policy_progress.py` + `nodes/policy_progress_node.py`
  - porque dependen de `plan_status` para `planner_request`.
- `backend/negotiation/progress_updater.py` + `nodes/progress_node.py`
  - porque consumen `policy_plan_judgement` legacy para counters/ledger.
- `backend/negotiation/schemas.py`
  - porque define shape mínimo persistente de `progress_state` y campos esperados por todo el grafo.

### 7.2 Campos legacy que hoy habría que conservar como “compat inerte” para no romper

- `policy_plan_judgement.plan_status`
- `progress_state.policy_state.planner_request`
- `progress_state.active_plan` (aunque sea mínimo)
- `state.executor_instruction` (aunque sea mínimo)
- `progress_state.plan_ledger` estructura básica
- `same_step_no_progress_turns` / `no_progress_same_step_turns`

### 7.3 Tests actuales a revisar por dependencia de schema legacy

Clases de tests afectados por dependencia explícita:
- tests de `policy_progress` (transiciones por `plan_status`, `planner_request`).
- tests de planner invariants (`active_plan`, `executor_instruction`, structured output v2).
- tests de world judge contract (shape v1/evidence/skip_planner).
- tests de executor/prompt contract ligados a step-instruction.

---

## Tabla final de bloqueo

| Componente | Qué espera hoy | Por qué bloquea el sistema nuevo | Archivo(s) / Función(es) |
|---|---|---|---|
| WORLD_JUDGE | Schema v1 con `plan_status/evidence/skip_planner/missing_signals` + post-guardrails | El output semántico nuevo se normaliza/degrada al contrato legacy; no persiste como contrato nuevo puro | `backend/prompts.py` (`WORLD_JUDGE_V2_*`), `backend/negotiation/nodes/world_node.py` (`world_judge_llm`, `_normalize_judgement`, `_post_normalize_evidence_guardrails`, `_build_evidence_candidates`) |
| POLICY_PROGRESS | `plan_status` en set legacy para computar `planner_request` | Sin `plan_status` legacy, la máquina de transición no opera como espera el pipeline | `backend/negotiation/policy_progress.py` (`update_policy_state`), `backend/negotiation/nodes/policy_progress_node.py` |
| PLANNER | `PlannerV2DecisionModel` estricto + `with_structured_output` | `planner_semantic_v1` sin `policy_id/active_plan/executor_instruction` produce validation error y fallback legacy | `backend/negotiation/phase_policy_planner.py` (`plan_phase_policy`), `backend/negotiation/elementos/strategy_definitions.py` (`PlannerV2DecisionModel`) |
| PLANNER NODE | Gates por `judge_status/skip_planner/no_progress`, y uso de `active_plan` | Mantiene control flow legacy basado en plan/status/counters | `backend/negotiation/nodes/planner_node.py` (`phase_policy_planner_node`, `_build_executor_instruction`, validaciones de ledger/blocked topics) |
| EXECUTOR | Prompt user con `executor_instruction_json` + postvalidaciones por step/question/slots | Sin contrato step-driven, hay desalineación de prompt, enforcement y compliance checks | `backend/negotiation/elementos/render/executor_prompts.py`, `backend/negotiation/executor/render_executor.py`, `backend/negotiation/nodes/executor_node.py` |
| PROGRESS/SCHEMAS | `progress_state` con counters + `plan_ledger` + `active_plan` | El estado persistente y consumidores dependen de estructuras legacy en múltiples nodos | `backend/negotiation/schemas.py`, `backend/negotiation/progress_updater.py`, `backend/negotiation/nodes/progress_node.py` |
