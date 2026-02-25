# Cleanup candidates — POLICY_PROGRESS

## Source of truth (runtime activo)
- `policy_progress_node` sigue en el grafo entre belief y planner.
- `update_policy_state` actúa como bridge inocuo y fuerza `planner_request = "replan_policy"`.

---

## Candidate PP-1
1) **Qué es**
- Nodo completo `backend/negotiation/nodes/policy_progress_node.py`.

2) **Por qué parece casi inerte**
- No decide flujo por `plan_status`; solo copia estado base y metadatos.
- Planner node ya está “always on semantic_planner_always_on”.

3) **Quién lo consumía antes**
- Traductor de `policy_plan_judgement.plan_status -> planner_request/advance_step`.

4) **Quién consume ahora**
- Runtime semántico lo usa como puente para mantener shape/state intermedio.

5) **Riesgo de borrarlo**
- Medio: puede afectar contratos de estado y tests de invariantes del grafo.

6) **Plan de eliminación**
- Opción A: eliminar nodo del grafo y mover inicializaciones mínimas al planner node.
- Opción B: mantener nodo pero reducirlo a pass-through explícito.

7) **Clasificación**
- **Requires refactor**.

---

## Candidate PP-2
1) **Qué es**
- Firma legacy de `update_policy_state(...)` con params no usados: `policy_plan_judgement`, `active_plan_status`, `judgement_missing_streak`, etc.

2) **Por qué es candidato**
- Se eliminan con `del` al inicio; ruido de compat.

3) **Quién lo consumía antes**
- Lógica de transiciones policy-driven con estado del plan.

4) **Quién consume ahora**
- Ninguna lógica funcional; solo compat API.

5) **Riesgo de borrarlo**
- Bajo-medio: impacta callers/tests que pasan argumentos posicionales.

6) **Plan de eliminación**
- Crear versión de firma semantic-only con kwargs mínimos y wrapper temporal.

7) **Clasificación**
- **Quick win** con wrapper.

---

## Candidate PP-3
1) **Qué es**
- Conservación de `policy_plan_judgement` en estado al final del nodo.

2) **Por qué es candidato**
- Semánticamente ya no es motor de planner.

3) **Quién lo consumía antes**
- Gating del planner legacy.

4) **Quién consume ahora**
- `progress_updater` y debug/invariants.

5) **Riesgo de borrarlo**
- Medio: romper tests y herramientas que inspeccionan esa key.

6) **Plan de eliminación**
- Mantener como shim hasta que `progress_updater` deje de depender de campos plan-driven.

7) **Clasificación**
- **Requires refactor**.
