# Cleanup candidates — PLANNER

## Source of truth (runtime activo)
- Nodo activo: `backend/negotiation/nodes/planner_node.py::phase_policy_planner_node`.
- Planner activo: `backend/negotiation/phase_policy_planner.py::plan_phase_policy`.
- Modelo activo: `PlannerSemanticV1DecisionModel` con `with_structured_output`.
- Output activo: `state["planner_semantic_output"]`.

---

## Candidate P-1
1) **Qué es**
- `backend/negotiation/elementos/strategy_definitions.py`
- Modelo `PlannerV2DecisionModel` + submodelos `PlannerV2ActivePlanModel`, `PlannerV2ExecutorInstructionModel`, `PlannerV2StepModel`.

2) **Por qué parece muerto en runtime semántico**
- `plan_phase_policy` usa `PlannerSemanticV1DecisionModel`.
- `rg` de callsites de `PlannerV2DecisionModel` devuelve solo la definición.

3) **Quién lo consumía antes**
- Planner V2 con `active_plan/executor_instruction` step-driven.

4) **Quién consume ahora**
- Ningún callsite runtime semántico.

5) **Riesgo de borrarlo**
- Posibles tests legacy/imports de typing internos.

6) **Plan de eliminación**
- Añadir chequeo de imports/test references.
- Eliminar modelos v2 y actualizar fixtures/tests dependientes.

7) **Clasificación**
- **Quick win** si no hay dependencias ocultas; si las hay, **requires refactor**.

---

## Candidate P-2
1) **Qué es**
- Prompts legacy planner:
  - `backend/prompts.py`: `PLANNER_V2_SYSTEM_PROMPT`, `PLANNER_V2_USER_PROMPT`.

2) **Por qué parece no activo**
- Runtime usa `PLANNER_SEMANTIC_V1_*`.
- Referencias de V2 se concentran en tests de formato legacy.

3) **Quién lo consumía antes**
- `plan_phase_policy` legacy v2.

4) **Quién consume ahora**
- Tests: `test_phase_policy_prompt_format.py`.

5) **Riesgo de borrarlo**
- Ruptura de tests/documentación/benchmarks que inspeccionan el prompt.

6) **Plan de eliminación**
- Congelar prompt V2 en docs estáticas y retirar de runtime bundle.

7) **Clasificación**
- **Quick win** tras migrar tests.

---

## Candidate P-3
1) **Qué es**
- Parámetros legacy todavía presentes en firma de `plan_phase_policy`: `allowed_policy_ids`, `judge_result`, etc., luego descartados con `del`.

2) **Por qué es candidato**
- Son argumentos inertes; ruido de compat.

3) **Quién lo consumía antes**
- Pipeline planner_v2 con gates y catálogo de policies.

4) **Quién consume ahora**
- Nadie funcionalmente (se descartan al inicio).

5) **Riesgo de borrarlo**
- Posible impacto en callers externos que aún pasan esos args.

6) **Plan de eliminación**
- Introducir firma v2-semantic estricta, mantener wrapper transitorio.

7) **Clasificación**
- **Requires refactor** por compat de interfaz.

---

## Candidate P-4
1) **Qué es**
- Inconsistencia de import en planner:
  - `backend/negotiation/phase_policy_planner.py` usa `from prompts import ...`

2) **Por qué es candidato/riesgo**
- El resto del runtime negocia prompts vía `repo_prompts`/path de paquete.
- `from prompts import ...` depende de layout de ejecución y puede fallar en packaging.

3) **Quién lo consumía antes**
- Patrón legacy de import directo del módulo raíz.

4) **Quién consume ahora**
- Path activo del planner semántico.

5) **Riesgo de borrarlo/cambiarlo**
- Bajo-medio, pero toca resolución de imports en entorno de ejecución.

6) **Plan de eliminación**
- Unificar imports de prompts en una sola puerta (`repo_prompts` o `backend.prompts`).

7) **Clasificación**
- **Quick win** (hardening) con validación de tests de import.
