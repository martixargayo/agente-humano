# LEGACY_PURGE_PLAN

## Objetivo
Dejar el repo en modo **semantic-only runtime** con flujo activo:
`semantic_judge -> progress_state.semantic_ledger -> planner_semantic_output -> executor`.

---

## Fase 0 — P0/P1 previos
### Qué se borra
- Se retiran lecturas/escrituras legacy asociadas a compat de juicio legacy y campos de plan rígido.

### Qué se reemplaza
- Canonicalización única de contexto reciente:
  - `state["assistant_last_message"] = state.get("assistant_last_message") or state.get("last_assistant_message") or ""`
- Fallback de lectura en prompt assembly planner/executor/world.

### Verificación
- `rg -n "assistant_last_message|last_assistant_message" backend -S`
- `python -m py_compile ...` (módulos tocados)

---

## Fase 1 — Purga de prompts/modelos/tests legacy
### Qué se borra
- Prompts legacy V1/V2 de planner/judge en runtime bundle.
- Tests legacy completos (`backend/tests/*`), conservando solo `test_semantic_runtime_v1.py`.

### Qué se reemplaza
- `backend/prompts.py` queda semantic-only:
  - `WORLD_JUDGE_V3_*`
  - `PLANNER_SEMANTIC_V1_*`
  - prompts de summary mínimos.
- `backend/negotiation/repo_prompts.py` exporta solo prompts activos.

### Verificación
- `rg -n "WORLD_JUDGE_V2|PLANNER_V2|planner_v2" backend -S`
- `pytest -q backend/tests/test_semantic_runtime_v1.py`

---

## Fase 2 — Purga internals legacy del judge
### Qué se borra
- Normalizers/guardrails/evidence helpers legacy del judge.

### Qué se reemplaza
- `world_judge_llm` con parse semántico mínimo:
  - valida `schema_version/topic_alignment/semantic_ledger`
  - fallback semántico neutro

### Verificación
- `rg -n "_normalize_judgement|_post_normalize_evidence_guardrails|evidence_candidates" backend -S`
- `python -m py_compile backend/negotiation/nodes/world_node.py`

---

## Fase 3 — Purga modelos planner V2
### Qué se borra
- `PlannerV2*` y submodelos step-driven.

### Qué se reemplaza
- `PlannerSemanticV1DecisionModel` como único contrato estructurado del planner.

### Verificación
- `rg -n "PlannerV2DecisionModel|PlannerV2ActivePlanModel|executor_instruction|active_plan" backend -S`
- `python -m py_compile backend/negotiation/elementos/strategy_definitions.py`

---

## Fase 4 — Purga estado/motor legacy
### Qué se borra
- `plan_ledger`, counters anti-loop, campos de plan rígido del estado y updater.

### Qué se reemplaza
- `progress_state.semantic_ledger` como memoria principal.
- `update_progress_state` reducido a persistencia semántica + debug mínimo.

### Verificación
- `rg -n "plan_ledger|blocked_topics|same_step_no_progress_turns|loop_flags|active_plan_status|active_plan" backend -S`
- `python -m py_compile backend/negotiation/schemas.py backend/negotiation/progress_updater.py backend/negotiation/nodes/executor_node.py`

---

## Fase 5 — Purga enforcement step-driven del executor
### Qué se borra
- Dependencia de instrucciones step-driven y compliance legacy.

### Qué se reemplaza
- Executor semántico: prompt con
  - `planner_semantic_output_json`
  - `semantic_ledger_json`
  - contexto reciente
- Determinismo permitido:
  - contrato JSON parseable
  - límites de estilo (`max_words/max_questions`)
  - prohibición de acciones físicas en prompt

### Verificación
- `rg -n "_enforce_executor_instruction|_instruction_followed|executor_instruction" backend -S`
- `python -m py_compile backend/negotiation/nodes/executor_node.py backend/negotiation/executor/render_executor.py`

---

## Fase 6 — Grafo semantic-only
### Qué se borra
- Dependencia funcional de policy-progress legacy como motor.

### Qué se reemplaza
- `negotiation_graph.py` simplificado y secuencial semantic-only.

### Verificación
- `python -m py_compile backend/negotiation/negotiation_graph.py backend/negotiation/policy_progress.py backend/negotiation/nodes/policy_progress_node.py`
- Smoke de 3 turnos (motivo de venta no se repite en turno 3)
- `pytest -q backend/tests/test_semantic_runtime_v1.py`

---

## Criterio de salida
Comando final obligatorio:
- `rg -n "planner_v2|WORLD_JUDGE_V2|PLANNER_V2|plan_status|evidence_candidates|success_criteria|active_plan|executor_instruction|plan_ledger" backend -S`

Resultado esperado: **0 matches** en código backend runtime.
