# Runtime semantic v1 IMPLEMENTED — judge → ledger → planner → executor

## Call graph final (runtime activo)

`world_updater -> belief_updater -> policy_progress (bridge inocuo) -> phase_policy_planner (semantic) -> progress_updater -> executor`

Flujo semántico efectivo por turno:
1. `world_judge_llm` produce `state.semantic_judge` (`judge_semantic_v1`).
2. `progress_updater` persiste `progress_state.semantic_ledger` desde `semantic_judge.semantic_ledger`.
3. `phase_policy_planner` produce `planner_semantic_v1` en `state.planner_semantic_output`.
4. `executor` renderiza con `planner_semantic_output_json + semantic_ledger_json`.

## Parsing final

### Judge (`backend/negotiation/nodes/world_node.py`)
- Prompt runtime: `WORLD_JUDGE_V3_SYSTEM_PROMPT` + `WORLD_JUDGE_V3_USER_PROMPT`.
- Validación mínima:
  - `schema_version == "judge_semantic_v1"`
  - `topic_alignment in {"on_topic","off_topic"}`
  - `semantic_ledger` con las 3 listas (normalizadas, fallback a prev/default vacío).
- Fuera del camino crítico: normalización/evidence legacy.

### Planner (`backend/negotiation/phase_policy_planner.py`)
- Structured output activo: `PlannerSemanticV1DecisionModel` (`extra="forbid"`).
- Prompt runtime: `PLANNER_SEMANTIC_V1_SYSTEM_PROMPT` + `PLANNER_SEMANTIC_V1_USER_PROMPT`.
- Inputs clave: `semantic_ledger_json`, `phase_map_json`, contexto reciente (`user_message`, `assistant_last_message`, `recent_history_text`).
- Fallback: semántico neutro (`planner_semantic_v1`), sin reactivar planner_v2.

### Executor (`backend/negotiation/executor/render_executor.py` + `executor_prompts.py`)
- Prompt runtime semántico (manteniendo output `executor_v2` por compat).
- Inputs centrales:
  - `planner_semantic_output_json`
  - `semantic_ledger_json`
  - `assistant_last_message`
  - `recent_history_text`
- Parsing mantenido: `safe_json_load` + `normalize_executor_output`.

## Schemas finales

### Progress state
- Se añadió `progress_state.semantic_ledger` con default estable:
  - `lo_que_ya_se_toco: []`
  - `lo_que_ya_pregunte: []`
  - `lo_que_falta_pero_no_insistire: []`

### Planner semantic model
- `PlannerSemanticV1DecisionModel`:
  - `schema_version="planner_semantic_v1"`
  - `phase` enum 5 fases
  - `style`
  - `next_move_hint`
  - `what_not_to_repeat`

## Fallbacks implementados (solo semánticos neutros)

- Judge: fallback `judge_semantic_v1` neutro con ledger previo/default.
- Planner: fallback `planner_semantic_v1` neutro (`clima_humano`, hint no insistente).
- Executor: se mantiene fallback neutral existente del renderer, sin contract step-driven obligatorio.

## Archivos y funciones cambiadas

- `backend/negotiation/schemas.py`
  - `SemanticLedger`, `default_semantic_ledger`, `ProgressState.semantic_ledger`, defaults.
- `backend/prompts.py`
  - `WORLD_JUDGE_V3_*`, `PLANNER_SEMANTIC_V1_*`.
- `backend/negotiation/repo_prompts.py`
  - exports de prompts V3/semantic.
- `backend/negotiation/nodes/world_node.py`
  - `world_judge_llm` semántico V3 + normalización mínima de ledger.
  - persistencia de `state.semantic_judge` + compat inerte en `policy_plan_judgement`.
- `backend/negotiation/policy_progress.py`
  - bridge inocuo (sin motor por plan_status).
- `backend/negotiation/elementos/strategy_definitions.py`
  - `PlannerSemanticV1DecisionModel`.
- `backend/negotiation/phase_policy_planner.py`
  - planner semántico runtime + structured output nuevo.
- `backend/negotiation/nodes/planner_node.py`
  - ruta simplificada sin gates legacy; set de `planner_semantic_output`.
- `backend/negotiation/elementos/render/executor_prompts.py`
  - prompts executor semánticos (manteniendo schema `executor_v2`).
- `backend/negotiation/executor/render_executor.py`
  - nuevo prompt assembly con `planner_semantic_output_json` + `semantic_ledger_json`.
- `backend/negotiation/nodes/progress_node.py`
  - pasa `semantic_judge` al updater.
- `backend/negotiation/progress_updater.py`
  - persistencia de `semantic_ledger` + debug truncado.
- `backend/negotiation/nodes/policy_progress_node.py`
  - usa `semantic_judge` para estado de presencia y bridge.
- `backend/tests/test_semantic_runtime_v1.py`
  - tests mínimos judge/planner/progress/E2E motivo de venta.

## Legacy retirado del camino crítico

1. Judge legacy como motor:
- `_normalize_judgement`
- `_post_normalize_evidence_guardrails`
- `_build_evidence_candidates` y helpers de evidence
- prompts `WORLD_JUDGE_V2_*` (no activos en path semántico)

2. Policy progress legacy como motor:
- traducción funcional `plan_status -> planner_request/advance_step`

3. Planner v2 como motor:
- `PlannerV2DecisionModel` y `with_structured_output(PlannerV2DecisionModel)` fuera del path activo.
- gates por `judge_status/skip_planner/no_progress/active_plan` fuera del planner node activo.

4. Executor step-driven como motor:
- `executor_instruction_json` ya no es input central del prompt activo.
- compliance step-driven no gobierna flujo semántico.

## Reproducción del caso “¿por qué lo vendes?”

1. Turno A:
- assistant pregunta motivo de venta.
- user responde útil o vago.
- judge actualiza `semantic_ledger` con:
  - `lo_que_ya_pregunte`: “Pregunté por qué lo vendes.”
  - `lo_que_ya_se_toco` o `lo_que_falta_pero_no_insistire` según respuesta.

2. Turno B:
- planner recibe `semantic_ledger` y produce `planner_semantic_v1` evitando repetir el motivo.
- executor responde en línea con `next_move_hint`, sin reabrir interrogatorio del mismo tema.

Señal esperada en trace/debug:
- `state.semantic_judge` presente.
- `progress_state.semantic_ledger` persistido.
- `state.planner_semantic_output.schema_version == "planner_semantic_v1"`.
