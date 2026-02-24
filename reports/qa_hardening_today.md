# QA Hardening Today

## A) Archivos tocados hoy (referencia para testing)

Comando usado: `git diff --name-only HEAD~1..HEAD`

### world_extractor / merge world / conflicts
- *(sin cambios directos en el último commit mergeado; cobertura añadida en tests)*

### world_judge + guardrails (skip_planner, interrupted_replan)
- `backend/tests/test_judge_advisor_v2_prompts.py`

### plan_ledger + retry_guard + policy_progress/planner gate + executor enforcement
- `backend/tests/test_executor_output_shape.py`
- `backend/tests/test_executor_plan_compliance.py`

### human-first prompts + wiring advisor_recs→executor
- `backend/negotiation/advisor.py`
- `backend/negotiation/elementos/render/executor_prompts.py`
- `backend/negotiation/executor/render_executor.py`
- `backend/prompts.py`
- `backend/tests/test_judge_advisor_v2_prompts.py`
- `backend/tests/test_executor_output_shape.py`
- `backend/tests/test_executor_plan_compliance.py`

---

## B) Unit tests obligatorios

- ✅ B1 world extractor (multi-item, slot-filling, respuestas cortas sin vacío, contradicciones) cubierto con nuevos/ajustados tests en `test_world_extractor_v4_multisignal_context_contradictions.py`.
- ✅ B2 world judge (invariante skip_planner + cambio explícito de objetivo con evidencia) cubierto en `test_world_judge_contracts.py`.
- ✅ B3 retry guard (3er intento, reached, loop flag, enforcement en policy/planner/executor) cubierto en `test_retry_guard_enforcement.py` y `test_hardening_integration_turns.py`.
- ✅ B4 human-first (normalización advisor, wiring ADVISOR_RECS_JSON, contrato answer_then_bridge + ask exacta) cubierto en `test_judge_advisor_v2_prompts.py`, `test_executor_output_shape.py`, `test_executor_plan_compliance.py`.

## C) Integration tests (mini-turnos)

Escenarios implementados en `backend/tests/test_hardening_integration_turns.py`:
- ✅ C1 “Mantenimiento + oferta”.
- ✅ C2 “Loop 3 intentos”.
- ✅ C3 “Human desvío 1 turno”.

## D) Runner manual reproducible (CLI)

Script creado: `scripts/manual_mustang_qa_runner.py`

Salida por turno incluye:
- `plan_id`, `step_idx`, `intent_id`
- `judge.plan_status`, `skip_planner`, `missing_signals`
- `retry_guard.key`, `attempts`, `reached`
- deltas de buckets de world
- flag de human_first + verificación de ask final exacta

## E) Ejecución y diagnóstico

### Ejecución enfocada (nuevos tests + áreas tocadas)
- ✅ Pass.

### Ejecución completa `pytest -q`
- ❌ Falla masiva preexistente fuera de las 4 áreas de hardening validadas hoy.

Clasificación de fallos observados:
1. **Regresiones por cambios de schema/normalización**
   - Múltiples tests esperan shape legacy de belief/world (`universal/negotiation`) pero runtime usa shape nuevo (`planner_signals/belief_buckets/schema_version`).
2. **Tests legacy incompatibles con defaults nuevos**
   - Tests con monkeypatch a símbolos removidos (`extract_belief_patch_llm_v3`) o warnings legacy ya no emitidos.
3. **Bugs reales de lógica (potenciales) pendientes de confirmar**
   - Casos en e2e/policy/state normalization que podrían mezclar incompatibilidad de contrato con lógica (requieren triage puntual por test).

## Invariantes garantizadas ahora (áreas objetivo)

- ✅ Judge: `skip_planner` nunca queda `true` si `plan_status != continue_same_step`.
- ✅ Retry guard: 3er intento mantiene `reached=true` y marca `loop_flags=max_attempts_reached:*`.
- ✅ Policy/planner/executor enforcement: con guard reached se fuerza replan/pivot y se bloquea repetición literal de pregunta.
- ✅ Human-first contract: `answer_then_bridge` mantiene puente y retoma ask final esperada.
- ✅ World extractor: no vacío en respuestas cortas con contexto, multi-señal y contradicciones preservadas.
