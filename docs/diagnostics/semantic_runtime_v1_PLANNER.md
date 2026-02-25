# Auditoría PLANNER — semantic runtime v1

## 1) Modelo runtime activo

### Confirmación de modelo activo
- Archivo: `backend/negotiation/phase_policy_planner.py`
- Uso activo:
  - `from .elementos.strategy_definitions import PlannerSemanticV1DecisionModel`
  - `structured = llm.with_structured_output(PlannerSemanticV1DecisionModel)`

### Confirmación de schema
- Archivo: `backend/negotiation/elementos/strategy_definitions.py`
- Modelo: `PlannerSemanticV1DecisionModel`
  - `schema_version = "planner_semantic_v1"`
  - `phase` enum 5 fases
  - `style`, `next_move_hint`, `what_not_to_repeat`
  - `extra="forbid"`

### Confirmación de NO uso de planner_v2 en path activo
- `PlannerV2DecisionModel` sigue definido en el repo, pero el path activo de `plan_phase_policy(...)` ya no lo consume.

## 2) Prompt assembly (inputs que entran)

En `plan_phase_policy(...)` se construye `user_prompt = PLANNER_SEMANTIC_V1_USER_PROMPT.format(...)` con:
- `semantic_ledger_json`
- `phase_map_json`
- `user_message`
- `assistant_last_message`
- `recent_history_text`
- `objective_summary`
- `full_profiles_block`
- `memory_short`, `memory_long`
- `advisor_recs_json`

Y luego:
- `SystemMessage(content=PLANNER_SEMANTIC_V1_SYSTEM_PROMPT)`
- `HumanMessage(content=user_prompt)`

### Inputs legacy removidos del assembly activo
No aparecen en el assembly activo:
- `allowed_policy_ids_json`
- `plan_ledger_json`
- `progress_counters_json`
- `active_plan_json`
- `judge_result_json` legacy v2
- `blocked_topics_json`

## 3) Salida y wiring

- `payload = result.model_dump()`
- `meta["planner_semantic_output"] = payload`
- `planner_node` toma ese output y lo mueve a:
  - `state["planner_semantic_output"]`
  - `state["phase_effective"]` derivado del `phase`

Además:
- `planner_node` marca compat inerte:
  - `state["executor_instruction"] = {}`
  - `progress_state["active_plan"] = None`
  - `progress_state["active_plan_status"] = "none"`

## 4) Fallback

Si falla invoke/parse:
- `phase_policy_planner.py` usa `_semantic_fallback()` con payload `planner_semantic_v1` (neutro).
- No hay fallback a `PlannerV2DecisionModel` ni a `active_plan` v2.

## 5) Prueba con ejemplo

### Estado de entrada (ejemplo)
- `semantic_ledger_json` incluye:
  - `lo_que_ya_pregunte`: ["Pregunté por qué lo vende."]
  - `lo_que_falta_pero_no_insistire`: ["Motivo exacto no quedó claro; no insistir."]
- `assistant_last_message`: “¿Por qué lo vendes?”
- `user_message`: “No lo sé exactamente.”

### Output esperado
```json
{
  "schema_version": "planner_semantic_v1",
  "phase": "descubrimiento_y_comprension",
  "style": "Calmo y práctico, sin insistir en lo ya tratado.",
  "next_move_hint": "Valida breve y pivota a precio/condiciones.",
  "what_not_to_repeat": [
    "No volver a preguntar por qué lo vende."
  ]
}
```

(El test `backend/tests/test_semantic_runtime_v1.py` valida justamente este patrón en `test_e2e_motivo_venta_semantic_no_repeat`).

## 6) Checklist PLANNER PASS/FAIL

- [PASS] `PlannerSemanticV1DecisionModel` activo en runtime.
- [PASS] `extra="forbid"` aplicado.
- [PASS] Prompt assembly usa ledger + phase_map + contexto reciente.
- [PASS] Output llega a `meta["planner_semantic_output"]` y `state["planner_semantic_output"]`.
- [PASS] Fallback es semántico, no planner_v2.
- [NEEDS_FIX/P0] Inconsistencia de clave: planner lee `assistant_last_message`, pero el graph setea `last_assistant_message`.
- [NEEDS_FIX/P0] Import `from prompts import ...` en módulo runtime (`phase_policy_planner.py`), sensible a entrypoint.
