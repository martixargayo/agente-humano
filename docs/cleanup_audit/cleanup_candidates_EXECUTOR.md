# Cleanup candidates — EXECUTOR

## Source of truth (runtime activo)
- Render activo: `backend/negotiation/executor/render_executor.py::render_executor_output`.
- Prompt activo: `EXECUTOR_USER_PROMPT` (alias de `EXECUTOR_V2_USER_PROMPT`) con `planner_semantic_output_json` y `semantic_ledger_json`.
- Nodo activo: `backend/negotiation/nodes/executor_node.py::executor_node`.

---

## Candidate E-1
1) **Qué es**
- `build_strategy_summary(...)["executor_instruction"]` en `render_executor.py`.

2) **Por qué parece legacy residual**
- `render_executor_output` ya no usa `strategy_summary.executor_instruction` para el prompt.
- Prompt semántico no tiene `executor_instruction_json`.

3) **Quién lo consumía antes**
- Plantilla step-driven del executor + checks de cumplimiento por step.

4) **Quién consume ahora**
- `executor_node` aún invoca enforcement con `state.get("executor_instruction", {})`.

5) **Riesgo de borrarlo**
- Puede cambiar comportamiento de post-validación y tests de compat step-driven.

6) **Plan de eliminación**
- Medir tests que dependen de enforcement por instruction.
- Mover enforcement a modo explícito legacy-only.

7) **Clasificación**
- **Requires refactor**.

---

## Candidate E-2
1) **Qué es**
- En `executor_node.py`: `_enforce_executor_instruction` + `_instruction_followed`.

2) **Por qué es candidato**
- Son checks step-driven heredados; con `executor_instruction={}` quedan casi inertes, pero código sigue ejecutando ramas y metadatos de compliance legacy.

3) **Quién lo consumía antes**
- Flujo `active_plan -> executor_instruction -> enforcement`.

4) **Quién consume ahora**
- Runtime semántico solo indirectamente (estado vacío), más telemetría.

5) **Riesgo de borrarlo**
- Puede afectar tests de `executor_plan_compliance` y cualquier modo legacy.

6) **Plan de eliminación**
- Dejar guardado detrás de feature flag o modo legacy.
- Mantener únicamente StyleContract + prohibiciones físicas + contrato JSON.

7) **Clasificación**
- **Requires refactor**.

---

## Candidate E-3
1) **Qué es**
- `_register_recent_question` en `executor_node.py` escribe `progress_state.plan_ledger.asked_questions_recent`.

2) **Por qué es candidato**
- Mantiene una memoria legacy paralela al `semantic_ledger`.

3) **Quién lo consumía antes**
- Anti-loop y planner v2 con `plan_ledger`.

4) **Quién consume ahora**
- `progress_updater`/debug legacy; no es input central del planner semántico.

5) **Riesgo de borrarlo**
- Romper tests o métricas que esperan `asked_questions_recent`.

6) **Plan de eliminación**
- Redirigir telemetría a `semantic_ledger` o `trace_runtime` y retirar escritura en `plan_ledger`.

7) **Clasificación**
- **Quick win** si se migra observabilidad; de lo contrario **requires refactor**.

---

## Candidate E-4
1) **Qué es**
- Parámetros de `render_executor_output` hoy inertes: `strategy_summary`, `memory_block`, `conversation_mode`, `policy_pack_active`, etc. usados mínimo o no usados para prompt semántico central.

2) **Por qué es candidato**
- Sobrecarga de interfaz de función heredada.

3) **Quién lo consumía antes**
- Prompt/executor legacy con resumen de planner step-driven.

4) **Quién consume ahora**
- Principalmente telemetría/contexto auxiliar.

5) **Riesgo de borrarlo**
- Impacto en llamadas desde `executor_node` y tests de integración.

6) **Plan de eliminación**
- Introducir firma más pequeña y wrapper de compat.

7) **Clasificación**
- **Requires refactor**.
