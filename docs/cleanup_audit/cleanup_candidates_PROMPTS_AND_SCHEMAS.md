# Cleanup candidates — PROMPTS and SCHEMAS

## Source of truth (runtime activo)
- Judge activo: `WORLD_JUDGE_V3_*` (consumido por `world_node.py`).
- Planner activo: `PLANNER_SEMANTIC_V1_*` + `PlannerSemanticV1DecisionModel`.
- Executor activo: `EXECUTOR_USER_PROMPT` (semántico) y contrato output `executor_v2`.
- Estado semántico activo: `progress_state.semantic_ledger`.

---

## Candidate PS-1
1) **Qué es**
- Duplicidad de prompts en `backend/prompts.py`: V2 legacy + V3/semantic coexistiendo en runtime bundle.

2) **Por qué es candidato**
- V2 no participa del call graph semántico; se conserva mayormente por tests/documentación.

3) **Quién lo consumía antes**
- Judge/Planner v2.

4) **Quién consume ahora**
- Tests de prompt format y docs internas.

5) **Riesgo de borrarlo**
- Rotura de tests snapshot/string assertions.

6) **Plan de eliminación**
- Mover texto V2 a docs estáticas; runtime exporta solo prompts activos.

7) **Clasificación**
- **Quick win** tras migración de tests.

---

## Candidate PS-2
1) **Qué es**
- `backend/negotiation/repo_prompts.py` exporta mezclado V2 + V3.

2) **Por qué es candidato**
- Punto de entrada de prompts debería exponer solo “activos” o segmentar por namespace (`legacy` vs `semantic`).

3) **Quién lo consumía antes**
- Tests y módulos legacy.

4) **Quién consume ahora**
- `world_node.py` usa V3 desde este módulo; tests usan V2.

5) **Riesgo de borrarlo**
- Tests que importan V2.

6) **Plan de eliminación**
- Crear `repo_prompts_legacy.py` y limpiar exports en `repo_prompts.py`.

7) **Clasificación**
- **Requires refactor** leve + ajustes de imports.

---

## Candidate PS-3
1) **Qué es**
- Schemas y defaults legacy aún centrales en `backend/negotiation/schemas.py`:
  - `active_plan`, `active_plan_status`, `plan_ledger`, counters anti-loop.

2) **Por qué es candidato**
- Runtime semántico requiere principalmente `semantic_ledger` + phase semántica + contrato executor_v2.

3) **Quién lo consumía antes**
- planner_v2 / policy_progress legacy / progress anti-loop.

4) **Quién consume ahora**
- Compat en `progress_updater`, `executor_node`, `progress_node`, tests legacy.

5) **Riesgo de borrarlo**
- Alto por dependencia transversal de tipos y tests.

6) **Plan de eliminación**
- Fasear schemas: `ProgressStateSemanticCore` + adapter legacy temporal.

7) **Clasificación**
- **Requires refactor** amplio.

---

## Candidate PS-4
1) **Qué es**
- Inconsistencia de estrategia de imports de prompts:
  - `phase_policy_planner.py` y `state/deps.py` usan `from prompts import ...`.
  - otros módulos usan `repo_prompts`.

2) **Por qué es candidato/riesgo**
- Puede fallar según PYTHONPATH/package root.

3) **Quién lo consumía antes**
- Patrón histórico de import absoluto local.

4) **Quién consume ahora**
- Path activo del planner y summary prompts.

5) **Riesgo de borrarlo/cambiarlo**
- Bajo si se ejecuta suite de imports.

6) **Plan de eliminación**
- Unificar en un solo estilo (`backend.prompts` o `repo_prompts`).

7) **Clasificación**
- **Quick win** de robustez.
