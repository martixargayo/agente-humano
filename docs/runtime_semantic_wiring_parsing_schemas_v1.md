# Runtime semantic v1 — Wiring + Parsing + Schemas (plan ejecutable)

> Objetivo: hacer **runnable** en runtime el sistema:
> JUDGE (scribe semántico) → progress_state.semantic_ledger → PLANNER semántico → EXECUTOR semántico
> sin reintroducir heurísticas/gates/counters/evidence como motor.
>
> Nota: aquí “determinismo permitido” = formato parseable (JSON shape, enums, límites de output).  
> “Determinismo prohibido” = reglas de control por contadores, keyword matching, evidence obligatoria, success_criteria, gates rígidos.

---

## 1) Plan de cambios a realizar (wiring + parsing + schemas)

### Milestone 0 — Preparación de contratos y schema mínimo (no cambia comportamiento)

Objetivo: que el runtime tenga dónde guardar y leer el ledger, aunque aún no lo use.

#### backend/negotiation/schemas.py

Añadir progress_state.semantic_ledger con shape:

lo_que_ya_se_toco: []

lo_que_ya_pregunte: []

lo_que_falta_pero_no_insistire: []

Default vacío y estable (nunca None).

Telemetría/trace (opcional, pero útil):

Asegurar que progress_debug y/o livetrace incluya semantic_ledger (truncado).

✅ No mete heurísticas ni determinismos. Es solo estado.

### Milestone 1 — Judge V3 (scribe) + parsing nuevo + persistencia del ledger (primer valor real)

Objetivo: que el judge nuevo se ejecute de verdad y que su output no sea destruido por normalizers/guardrails legacy.

#### backend/prompts.py

Añadir WORLD_JUDGE_V3_SYSTEM_PROMPT y WORLD_JUDGE_V3_USER_PROMPT (ya tenéis doc design-only).

#### backend/negotiation/nodes/world_node.py

Cambiar el “judge path” a:

construir user_prompt mínimo (user + assistant_last + recent_history + ledger_prev).

parsear JSON como judge_semantic_v1.

NO pasar por _normalize_judgement ni _post_normalize_evidence_guardrails.

Guardar el resultado en state["semantic_judge"] (o reemplazar policy_plan_judgement si decidís migrar ya).

#### backend/negotiation/progress_updater.py

Leer state["semantic_judge"].semantic_ledger y persistirlo en progress_state.semantic_ledger.

⚠️ Nota: en este milestone, si aún no cambias planner/executor, tendrás que decidir compat temporal:

Opción A (recomendada): mantener judge legacy en paralelo solo para que el resto no rompa (pero sin control de flujo, solo compat).

Opción B: hacer que policy_progress/planner node no dependan del judge legacy (si ya arrancáis Milestone 2).

### Milestone 2 — Planner semántico (parsing/model nuevo; fin del planner_v2 como motor)

Objetivo: que el planner deje de requerir PlannerV2DecisionModel y empiece a consumir semantic_ledger.

#### backend/negotiation/elementos/strategy_definitions.py

Crear PlannerSemanticV1Model (Pydantic) con:

schema_version="planner_semantic_v1"

phase (enum de tus 5 fases)

style (string)

next_move_hint (string)

what_not_to_repeat (list[str])

#### backend/negotiation/phase_policy_planner.py

Sustituir with_structured_output(PlannerV2DecisionModel) por PlannerSemanticV1Model.

Cambiar el prompt assembly: eliminar inputs legacy y añadir:

semantic_ledger_json

phase_map_json

contexto reciente (user + assistant_last + recent_history)

#### backend/negotiation/nodes/planner_node.py

Eliminar gates que dependen de:

plan_status

skip_planner

contadores no_progreso

active_plan

El nodo pasa a:

llamar siempre al planner semántico

poner output en state["planner_semantic_output"]

(opcional) construir un strategy_summary mínimo para observabilidad

#### backend/negotiation/policy_progress.py (+ node)

Convertirlo en no-op / bridge inocuo.

Eliminar su dependencia de plan_status como motor.

✅ Esto sigue alineado con “cero heurística”: no hay counters/gates/keywords controlando, solo I/O parseable.

### Milestone 3 — Executor semántico (cambio de inputs + suavizar enforcement)

Objetivo: que el executor deje de depender de executor_instruction_json (steps) y use:

planner_semantic_output_json

semantic_ledger_json

#### backend/negotiation/executor/render_executor.py + executor_prompts.py

Reemplazar placeholders executor_instruction_json → planner_semantic_output_json

Inyectar semantic_ledger_json

Añadir assistant_last_message y recent_history_text (para coherencia)

#### backend/negotiation/nodes/executor_node.py

Desactivar/retirar enforcement de “instruction-followed” cuando no existe step-instruction.

Mantener solo:

contrato JSON

límites de StyleContract (words/questions)

prohibición de pedir acciones físicas (esto sí lo queréis)

progress_updater:

puede seguir registrando asked_question como telemetría, pero ya no lo usáis como control.

### Milestone 4 — Limpieza: retirar legacy del camino crítico

Objetivo: que no queden “fantasmas” que reintroduzcan plan_status/evidence/skip.

Quitar:

_normalize_judgement, _post_normalize_evidence_guardrails, evidence candidates (o dejarlos muertos)

PlannerV2DecisionModel como ruta activa

active_plan y executor_instruction como centro del sistema

gates basados en same_step_no_progress_turns, loop_flags, blocked_topics, etc.

---

## 2) Documento único listo para crear en el repo

Copia/pega esto como:

docs/runtime_semantic_wiring_parsing_schemas_v1.md

# Runtime semantic v1 — Wiring + Parsing + Schemas (plan ejecutable)

> Objetivo: hacer **runnable** en runtime el sistema:
> JUDGE (scribe semántico) → progress_state.semantic_ledger → PLANNER semántico → EXECUTOR semántico
> sin reintroducir heurísticas/gates/counters/evidence como motor.
>
> Nota: aquí “determinismo permitido” = formato parseable (JSON shape, enums, límites de output).  
> “Determinismo prohibido” = reglas de control por contadores, keyword matching, evidence obligatoria, success_criteria, gates rígidos.

---

## 0) Estado actual (por qué rompe si solo cambiamos prompts)

### Bloqueador 1 — WORLD_JUDGE acoplado a schema legacy v1
- Parsing actual: `json.loads(...)` + `_normalize_judgement()` + `_post_normalize_evidence_guardrails()`.
- Esos pasos requieren `plan_status/evidence/missing_signals/skip_planner`.
- Resultado: si el LLM devuelve `judge_semantic_v1`, se degrada a legacy o cae en fallback.

### Bloqueador 2 — PLANNER acoplado a structured output `PlannerV2DecisionModel`
- `with_structured_output(PlannerV2DecisionModel)` exige `planner_v2` con `policy_id/active_plan/executor_instruction`.
- `planner_semantic_v1` no valida → excepción → fallback a legacy.

### Bloqueador 3 — EXECUTOR acoplado a `executor_instruction_json` (step-driven)
- Prompt y enforcement downstream esperan “pregunta final del step” y compliance.
- Sin `executor_instruction`, o se desalinean placeholders o se invalida la intención.

---

## 1) Contratos runtime (end-state)

### 1.1 Judge output: `judge_semantic_v1` (binario)
```json
{
  "schema_version": "judge_semantic_v1",
  "topic_alignment": "on_topic | off_topic",
  "reason_short": "string",
  "semantic_ledger": {
    "lo_que_ya_se_toco": ["string"],
    "lo_que_ya_pregunte": ["string"],
    "lo_que_falta_pero_no_insistire": ["string"]
  },
  "ledger_update_notes": "string"
}
```

### 1.2 progress_state mínimo persistente
```json
{
  "semantic_ledger": {
    "lo_que_ya_se_toco": ["string"],
    "lo_que_ya_pregunte": ["string"],
    "lo_que_falta_pero_no_insistire": ["string"]
  }
}
```

### 1.3 Planner output: planner_semantic_v1
```json
{
  "schema_version": "planner_semantic_v1",
  "phase": "clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo",
  "style": "string",
  "next_move_hint": "string",
  "what_not_to_repeat": ["string"]
}
```

### 1.4 Executor output: executor_v2 (se mantiene por compat)

Se mantiene el schema actual del executor (executor_v2) para no romper render/postproceso.

Se cambia qué inputs recibe en prompt (planner_semantic_output + semantic_ledger).

## 2) Wiring end-to-end (nuevo flujo real)

Turno T:

world_updater_node ejecuta world_judge_llm (v3)
Input mínimo = user_message + assistant_last_message + recent_history + semantic_ledger_prev
Output = judge_semantic_v1

progress_updater persiste progress_state.semantic_ledger = judge.semantic_ledger

phase_policy_planner llama al PLANNER semántico
Inputs: semantic_ledger + phase_map + contexto reciente
Output: planner_semantic_v1

executor renderiza texto usando:
planner_semantic_output + semantic_ledger + contexto reciente
Output: executor_v2

## 3) Parsing strategy (sin heurísticas)

### 3.1 Judge parsing (world_node.py)

Parseo JSON con validación mínima de shape:

keys obligatorias: schema_version, topic_alignment, semantic_ledger

topic_alignment solo on_topic|off_topic

semantic_ledger contiene 3 listas (si faltan, fallback a prev vacío)

Prohibido:

_normalize_judgement

_post_normalize_evidence_guardrails

evidence candidates

### 3.2 Planner parsing (phase_policy_planner.py)

with_structured_output(PlannerSemanticV1Model) (nuevo Pydantic)

extra="forbid" para evitar claves legacy colándose

Si falla:

fallback semántico mínimo (phase + hint neutro) sin reactivar planner_v2.

### 3.3 Executor parsing (render_executor.py)

Se mantiene safe_json_load + normalize_executor_output

Cambian placeholders y el prompt.

En executor_node, cualquier enforcement que dependía de step-instruction debe quedar inactivo o guardado detrás de “si hay executor_instruction”.

## 4) Cambios por archivo (lista operativa)

### 4.1 backend/negotiation/schemas.py

Añadir semantic_ledger al progress_state default.

### 4.2 backend/prompts.py

Añadir WORLD_JUDGE_V3_*

Añadir PLANNER_SEMANTIC_V1_* (o equivalente)

Añadir EXECUTOR_SEMANTIC_V1_* (o equivalente)

### 4.3 backend/negotiation/nodes/world_node.py

Nuevo path de judge:

payload mínimo + semantic_ledger_prev

parse judge_semantic_v1

persistir en state["semantic_judge"] (o similar)

Legacy normalizers/guardrails fuera del camino crítico.

### 4.4 backend/negotiation/progress_updater.py

Persistir semantic_ledger en progress_state.

No usar topic_alignment como control; solo telemetría.

### 4.5 backend/negotiation/phase_policy_planner.py

Reemplazar PlannerV2DecisionModel por PlannerSemanticV1Model.

Rehacer inputs (eliminar allowed_policies/plan_ledger/counters/active_plan).

Output en state["planner_semantic_output"].

### 4.6 backend/negotiation/nodes/planner_node.py

Quitar gates de:

judge_status

skip_planner

same_step_no_progress_turns

active_plan

Puente simple: planner_semantic_output → executor.

### 4.7 backend/negotiation/nodes/executor_node.py + render_executor.py

Cambiar prompt builder:

eliminar executor_instruction_json

añadir planner_semantic_output_json

añadir semantic_ledger_json

Desactivar checks “instruction followed” basados en steps.

### 4.8 backend/negotiation/policy_progress.py

Convertir a bridge inocuo o retirarlo del camino crítico si el grafo lo permite.

## 5) Compat temporal (para migración segura sin “gates”)

Durante transición, los campos legacy pueden existir, pero deben ser inertes (no usados como motor).

El fallback no debe reactivar planner_v2 salvo que explícitamente se habilite modo legacy.

## 6) Tests mínimos (para que sea implementable)

Judge: parsea y retorna judge_semantic_v1 válido.

Progress updater: persiste semantic_ledger turn-to-turn.

Planner: valida planner_semantic_v1 con Pydantic.

Executor: renderiza executor_v2 con asked_question opcional y respeta “no repetir” semánticamente.

E2E: turno con “¿por qué lo vendes?” → ledger registra lo_que_ya_pregunte y en el siguiente turno planner/executor no repreguntan.

---

## LISTA EXACTA DE COSAS A ELIMINAR / DEJAR FUERA DEL CAMINO CRÍTICO

1. **WORLD_JUDGE legacy (prompts + parsing + output fields)**
   1. `backend/prompts.py`
      - `WORLD_JUDGE_V2_SYSTEM_PROMPT` → dejar fuera del camino crítico (bloques: `plan_status`, `evidence`, `skip_planner`, `missing_signals`, `counters`).
      - `WORLD_JUDGE_V2_USER_PROMPT` → dejar fuera del camino crítico (PLAN CONTEXT + progress/evidence legacy).
   2. `backend/negotiation/nodes/world_node.py`
      - `_normalize_judgement` → eliminar/desactivar del path activo.
      - `_post_normalize_evidence_guardrails` → eliminar/desactivar del path activo.
      - `_build_evidence_candidates` + `_build_evidence_item` + `_normalize_evidence_items` + `_has_text_for_audit` + `_evidence_shows_new_information` + `_ALLOWED_EVIDENCE_SOURCES` → fuera del camino crítico.
   3. Campos legacy de output de judge fuera del camino crítico
      - `plan_status`
      - `evidence`
      - `missing_signals`
      - `skip_planner`
      - `degraded` / `degrade_reason` por evidence
      - forced replan por `same_step_no_progress_turns`

2. **POLICY_PROGRESS legacy (plan_status como motor)**
   1. `backend/negotiation/policy_progress.py`
      - lógica de traducción `plan_status -> planner_request/advance_step` como motor (`update_policy_state`).
   2. `backend/negotiation/nodes/policy_progress_node.py`
      - dependencia funcional de `policy_plan_judgement` legacy para dirigir flujo.

3. **PLANNER v2 legacy (schema/steps/gates)**
   1. `backend/prompts.py`
      - `PLANNER_V2_SYSTEM_PROMPT` fuera del camino crítico (bloques: `policy_id`, `active_plan` multi-step, `success_criteria`, anti-loop por counters, `plan_ledger`, `blocked_topics`).
      - `PLANNER_V2_USER_PROMPT` fuera del camino crítico (inputs legacy: `judge_result_json`, `allowed_policy_ids_json`, `policy_catalog_es_subset_json`, `active_plan_json`, `progress_counters_json`, `plan_ledger_json`, `blocked_topics_json`).
   2. `backend/negotiation/elementos/strategy_definitions.py`
      - `PlannerV2DecisionModel` como ruta activa (desplazar fuera del camino crítico).
   3. `backend/negotiation/phase_policy_planner.py`
      - `with_structured_output(PlannerV2DecisionModel)` fuera de ruta activa.
      - `_to_active_plan` y parsing centrado en steps/success_criteria fuera de ruta activa.
   4. `backend/negotiation/nodes/planner_node.py`
      - gates por `judge_status`, `skip_planner`, `same_step_no_progress_turns`, `active_plan`.
      - `validate_active_plan_against_ledger` fuera de motor.
      - lógica de `blocked_topics`/pivot legacy fuera de motor.

4. **PROGRESS counters/ledger usados como control**
   1. `backend/negotiation/progress_updater.py`
      - `same_step_no_progress_turns` / `no_progress_same_step_turns` / `loop_flags` / `plan_id_changes_window` como disparadores de control.
      - `plan_ledger` intent-based como motor (`resolved_intents`, `failed_intents`, `asked_questions_recent`, `blocked_topics`).

5. **EXECUTOR step-driven legacy**
   1. `backend/negotiation/elementos/render/executor_prompts.py`
      - dependencia de `executor_instruction_json` como input central en `EXECUTOR_V2_USER_PROMPT`.
      - cláusulas del system prompt orientadas a “pregunta final del step / retomar step”.
   2. `backend/negotiation/executor/render_executor.py`
      - wiring central a `executor_instruction_json` y `planner_output_summary` legacy.
   3. `backend/negotiation/nodes/executor_node.py`
      - enforcement `instruction-followed` cuando no existe step instruction.
      - checks de ask/ask_slots derivados del step como control de flujo.
