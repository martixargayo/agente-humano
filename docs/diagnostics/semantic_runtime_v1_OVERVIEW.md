# Auditoría runtime semántico v1 — OVERVIEW

## Resumen ejecutivo

Estado general del runtime `semantic_judge -> progress_state.semantic_ledger -> planner_semantic_output -> executor`:

- **Implementado y activo** en rutas principales de judge, planner y prompt del executor.
- **Persistencia de ledger** confirmada en `progress_updater`.
- **Bridge de policy_progress** efectivamente inocuo (sin plan_status como motor).
- **Riesgos P0 detectados**:
  1. Inconsistencia de clave `assistant_last_message` vs `last_assistant_message` en planner/executor.
  2. Imports `from prompts import ...` en módulos de runtime (riesgo de packaging/entrypoint).
- **Legacy no gobierna planner** (gates legacy retirados del planner node activo), pero aún hay “huellas legacy” no críticas en `progress_updater` y `world_updater` (campos auxiliares, counters/plan_ledger para telemetría/compat).

---

## Call graph final efectivo

Orden real de ejecución del grafo (source of truth):

`world_updater -> belief_updater -> policy_progress -> phase_policy_planner -> progress_updater -> executor`

Evidencia:
- `workflow.add_edge("world_updater", "belief_updater")`
- `workflow.add_edge("belief_updater", "policy_progress")`
- `workflow.add_edge("policy_progress", "phase_policy_planner")`
- `workflow.add_edge("phase_policy_planner", "progress_updater")`
- `workflow.add_edge("progress_updater", "executor")`
(`backend/negotiation/negotiation_graph.py`, bloque `workflow.add_edge(...)`).

---

## ANTES vs DESPUÉS (legacy -> semantic)

| Área | Antes | Después (actual) |
|---|---|---|
| Judge | `WORLD_JUDGE_V2` + normalize/evidence guardrails | `WORLD_JUDGE_V3` parse mínimo a `judge_semantic_v1` + fallback semántico |
| Estado | sin `semantic_ledger` persistente | `progress_state.semantic_ledger` tipado + default estable |
| Planner | `PlannerV2DecisionModel` + active_plan/policy_id | `PlannerSemanticV1DecisionModel` + `planner_semantic_output` |
| policy_progress | traducía `plan_status -> planner_request` | bridge inocuo (`planner_request = replan_policy`) |
| Executor input central | `executor_instruction_json` | `planner_semantic_output_json + semantic_ledger_json + contexto reciente` |

---

## Checks globales (PASS/FAIL/NEEDS_FIX)

1. JUDGE V3 activo y sin normalizers legacy en path activo → **PASS**.
2. Persistencia `semantic_ledger` turn-to-turn → **PASS**.
3. Planner usa `PlannerSemanticV1DecisionModel` y emite `state["planner_semantic_output"]` → **PASS**.
4. Executor consume `planner_semantic_output_json + semantic_ledger_json` y no `executor_instruction_json` → **PASS**.
5. `policy_progress` inerte (sin plan_status como motor) → **PASS**.
6. No “fantasmas” legacy en camino crítico → **NEEDS_FIX** (hay huellas legacy de compat/telemetría todavía presentes).
7. Solo determinismo permitido (schema + límites style + prohibición acciones físicas) → **PASS** en path activo.

---

## Riesgos detectados (priorizados)

### P0
1. **Inconsistencia de clave de contexto**
   - El estado del grafo construye `last_assistant_message`, pero planner/executor leen `assistant_last_message` en varios puntos.
   - Impacto: pérdida de contexto reciente en prompts semánticos (degradación de calidad/consistencia).

2. **Imports absolutos `from prompts import ...` en runtime package**
   - Visible en `phase_policy_planner.py` y `state/deps.py`.
   - Riesgo: ruptura según entrypoint/packaging cuando `prompts` no esté resoluble en `PYTHONPATH` raíz.

### P1
3. **`policy_plan_judgement` compat inerte con `schema_version="v1_compat_inert"`**
   - Puede afectar tooling/tests que esperen estrictamente `"v1"`.

### P2
4. **Código legacy aún presente (no activo) en world/progress**
   - No gobierna planner activo, pero añade ruido y confusión de mantenimiento.

---

## Documentos por componente

- [JUDGE auditoría](./semantic_runtime_v1_JUDGE.md)
- [PLANNER auditoría](./semantic_runtime_v1_PLANNER.md)
- [EXECUTOR auditoría](./semantic_runtime_v1_EXECUTOR.md)
