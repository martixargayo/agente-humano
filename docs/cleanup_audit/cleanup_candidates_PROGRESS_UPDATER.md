# Cleanup candidates — PROGRESS_UPDATER

## Source of truth (runtime activo)
- `update_progress_state` persiste correctamente `progress_state.semantic_ledger` tomando `semantic_judge.semantic_ledger`.
- Sigue calculando además múltiples señales legacy (`plan_ledger`, `loop_flags`, `same_step_no_progress_turns`).

---

## Candidate PU-1
1) **Qué es**
- Bloque anti-loop legacy en `update_progress_state`:
  - `plan_id_changes_window`
  - `same_step_no_progress_turns` / `no_progress_same_step_turns`
  - `loop_flags` (`continue_loop`, `replan_churn`, `stuck_in_policy`).

2) **Por qué es candidato**
- El flujo semántico actual no debería gobernarse por counters/gates legacy.
- Planner node ya no usa estos gates para decidir ejecución.

3) **Quién lo consumía antes**
- Judge/planner legacy para forzar replans y pivots por contador.

4) **Quién consume ahora**
- Principalmente debug y persistencia histórica.

5) **Riesgo de borrarlo**
- Medio-alto por tests de anti-loop y observabilidad existente.

6) **Plan de eliminación**
- Separar telemetría histórica del estado crítico.
- Mantener snapshots en trace, retirar como motor del estado.

7) **Clasificación**
- **Requires refactor**.

---

## Candidate PU-2
1) **Qué es**
- Motor `plan_ledger` legacy:
  - `_update_plan_ledger`
  - `_decay_and_apply_blocked_topics`
  - `_record_recent_question`
  - campos `resolved_intents`, `failed_intents`, `asked_questions_recent`, `blocked_topics`.

2) **Por qué es candidato**
- Runtime semántico ya usa `semantic_ledger` como memoria principal.

3) **Quién lo consumía antes**
- Planner v2 anti-repetición por intents + blocked topics.

4) **Quién consume ahora**
- Persistencia/debug y algunos módulos legacy.

5) **Riesgo de borrarlo**
- Alto por amplitud de referencias en tests (`test_plan_ledger.py`, `test_progress_updater.py`, etc.).

6) **Plan de eliminación**
- Primero marcar `plan_ledger` como telemetría read-only.
- Luego eliminar escrituras activas y limpiar consumidores.

7) **Clasificación**
- **Requires refactor**.

---

## Candidate PU-3
1) **Qué es**
- Funciones legacy de evidencia en updater: `_judge_has_evidence`, `_best_judge_evidence`, `_extract_current_intent_id`, etc.

2) **Por qué es candidato**
- Están orientadas a contratos `policy_plan_judgement` v1 + `active_plan`.

3) **Quién lo consumía antes**
- Flujo plan-driven de avance de steps.

4) **Quién consume ahora**
- Se siguen usando dentro de `_update_plan_ledger` legacy, no en path semántico principal.

5) **Riesgo de borrarlo**
- Afecta plan_ledger y tests legacy.

6) **Plan de eliminación**
- Eliminar en conjunto con PU-2.

7) **Clasificación**
- **Requires refactor**.

---

## Candidate PU-4
1) **Qué es**
- `progress_debug` en `progress_node.py` reporta `anti_loop_signals` y `counters_incremented` legacy como centro de telemetría.

2) **Por qué es candidato**
- Puede inducir lectura operacional legacy aunque el motor sea semántico.

3) **Quién lo consumía antes**
- Dashboard y diagnóstico de loops legacy.

4) **Quién consume ahora**
- UI/trace debug.

5) **Riesgo de borrarlo**
- Bajo-medio (impacto principalmente observabilidad).

6) **Plan de eliminación**
- Cambiar foco de debug a `semantic_ledger` + planner_semantic_output coherencia.

7) **Clasificación**
- **Quick win** de observabilidad semántica.
