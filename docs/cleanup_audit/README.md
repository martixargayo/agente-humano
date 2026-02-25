# Cleanup Audit — Semantic Runtime v1

## Resumen ejecutivo
Esta auditoría revisa qué quedó activo vs legacy después de activar el flujo semántico:

`world_updater (semantic_judge) -> policy_progress (bridge) -> phase_policy_planner (planner_semantic_v1) -> progress_updater (persist semantic_ledger) -> executor`.

Hallazgos principales:
- El **path activo semántico** está presente y ejecuta Judge V3 + PlannerSemanticV1 + Executor con `planner_semantic_output_json` y `semantic_ledger_json`.
- Sigue existiendo una **gran superficie legacy no eliminada** (judge normalizers/evidence, planner v2 models/prompts, plan_ledger/counters, enforcement step-driven del executor) que en varios casos ya no gobierna el flujo, pero sí agrega costo de mantenimiento y riesgo de regresión.
- Hay piezas con uso residual para **tests/back-compat/tooling**, por lo que la limpieza debe ser por fases.

## Metodología y criterio de “candidato muerto”
Comandos usados como evidencia mínima:
- `rg -n "world_updater_node|world_judge_llm|phase_policy_planner_node|executor_node|policy_progress_node|update_progress_state|plan_phase_policy|render_executor_output" backend/negotiation -S`
- `rg -n "WORLD_JUDGE_V2|PLANNER_V2|PlannerV2DecisionModel|executor_instruction_json|_normalize_judgement|_post_normalize_evidence_guardrails|evidence_candidates|skip_planner|missing_signals|active_plan|success_criteria|plan_ledger|blocked_topics|loop_flags|same_step_no_progress_turns" backend docs -S`
- `rg -n "from prompts import|from \.?repo_prompts import" backend/negotiation -S`
- Búsqueda de callsites puntuales por símbolo para diferenciar “definido” vs “referenciado en runtime”.

Criterio:
1. **Dead candidate**: no aparece en el call graph activo ni tiene callsite runtime (solo definición/tests/docs).
2. **Legacy inerte**: todavía se ejecuta, pero no es motor de control del flujo semántico.
3. **Compat required (temporal)**: parece legacy, pero suprimirlo rompe tests/tooling/compat actual.

## Call graph ANTES vs DESPUÉS
### Antes (legacy plan-driven)
`world_judge_v2 -> normalize/evidence guardrails -> policy_progress(plan_status) -> planner_v2(active_plan/executor_instruction) -> executor step-driven`

### Después (semantic runtime v1)
`world_updater_node(world_judge_llm v3) -> state.semantic_judge`
`-> policy_progress_node(bridge inocuo)`
`-> phase_policy_planner_node(plan_phase_policy + PlannerSemanticV1DecisionModel)`
`-> progress_updater_node(update_progress_state persiste semantic_ledger)`
`-> executor_node(render_executor_output con planner_semantic_output_json + semantic_ledger_json)`

## Priorización de limpieza
### P0 (quick wins, bajo riesgo)
1. Eliminar rutas judge legacy no llamadas por runtime activo (normalizers/evidence helpers) cuando se ajusten tests legacy.
2. Despublicar/aislar prompts legacy V2 no usados en runtime activo.
3. Consolidar imports de prompts (`from prompts import ...`) hacia una ruta única (`repo_prompts` o paquete absoluto) para reducir fragilidad de packaging.

### P1 (requiere coordinación)
1. Desacoplar `progress_updater` del motor legacy (`plan_ledger`, `loop_flags`, `same_step_no_progress_turns`) que aún se computa.
2. Reducir enforcement step-driven en `executor_node` que todavía evalúa `executor_instruction` por compat.
3. Retirar `PlannerV2DecisionModel` y submodelos cuando se limpien tests y contratos heredados.

### P2 (refactor amplio)
1. Normalizar schemas y tipos para remover `active_plan`/`plan_ledger` del estado crítico.
2. Purgar tests/documentación legacy y moverlos a carpeta “legacy_archive”.

## Índice de documentos
- `cleanup_candidates_JUDGE.md`
- `cleanup_candidates_PLANNER.md`
- `cleanup_candidates_EXECUTOR.md`
- `cleanup_candidates_POLICY_PROGRESS.md`
- `cleanup_candidates_PROGRESS_UPDATER.md`
- `cleanup_candidates_PROMPTS_AND_SCHEMAS.md`
