# Plan actualizado v3 — migración a flujo LLM-first dominante

```text
world_updater (intocable) + world_judge_llm (siempre-on, separado)
  -> belief_updater (intocable)
  -> policy_progress (router mínimo)
  -> phase_policy_planner (gate + plan + handoff)
  -> progress_updater (persistencia + anti-loop seguridad)
  -> executor
```


## Ajustes finos cerrados
- Regla dura de evidencia: si `plan_status` llega como `advance_step` o `completed` con `evidence=[]`, se degrada a `continue_same_step` con `degraded=true` y `degrade_reason="missing_evidence_for_progress"`.
- Señal `advance_step`: se transporta en `progress_state["advance_step"]` (top-level de progreso) para no contaminar `PolicyState` legacy.
- Sin flags para existencia del judge: ante caída LLM se emite fail-safe degradado y se traza `judge_error_type` + `judge_latency_ms`.

## 1) Arquitectura final (6 nodos) y responsabilidades exactas

### Nodo 1 — `world_updater` + `world_judge_llm`
- **Qué se mantiene igual (intocable):** `update_world_state(...)`, gating world, diffs y merge de world abierto.
- **Qué se añade:** `world_judge_llm(...)` como función separada y aislada dentro de `world_node.py`.
- **Regla dura:** `world_judge_llm` corre **siempre** en cada turno y escribe **siempre** `state["policy_plan_judgement"]` (nunca `None`).
- **Fuente principal de decisión:** LLM.
- **Fallback permitido:** solo fail-safe degradado cuando falle LLM/parseo/timeout, marcado con `degraded=true` y `degrade_reason` explícito.

### Nodo 2 — `belief_updater`
- Se conserva sin cambios funcionales (gating + actualización belief actual).
- No toma decisiones de control-flow.

### Nodo 3 — `policy_progress` (router mínimo)
- Se reduce a switch determinista por `policy_plan_judgement.plan_status`.
- No hace lógica legacy (attempts/slots/success/phase-recheck).
- Produce `planner_request` (+ `advance_step=true` si corresponde).

### Nodo 4 — `phase_policy_planner`
- Gate único por: `planner_request` + `active_plan` + `advance_step`.
- `continue_policy` + plan vigente => skip LLM planner.
- `advance_step=true` => avanzar `active_plan.current_step_idx` sin planner LLM (salvo out-of-range).
- `replan_policy`/sin plan/interrupción => planner LLM crea/actualiza plan.
- Siempre emite `executor_instruction`.

### Nodo 5 — `progress_updater`
- Solo persistencia + anti-loop seguridad + telemetría.
- No pisa campos de control-flow decididos este turno.

### Nodo 6 — `executor`
- Consume `executor_instruction` como contrato autoritativo.
- Se añade enforcement mínimo post-LLM para `safe_mode`, `must_avoid`, y límites de preguntas.

---

## 2) Cambios por archivo (qué se toca y qué NO se toca)

## A tocar

1. `backend/negotiation/nodes/world_node.py`
- Añadir `world_judge_llm(...)` separado.
- Integrar su invocación **después** del world update actual, sin alterar la lógica existente de update/gating/diff.
- Garantizar asignación incondicional de `state["policy_plan_judgement"]`.

2. `backend/negotiation/policy_progress.py`
- Reducir `update_policy_state(...)` a router mínimo por `plan_status`.
- Eliminar ruta legacy de evaluación de éxito, attempts, slots y phase recheck.

3. `backend/negotiation/nodes/policy_progress_node.py`
- Simplificar a: leer judgement válido -> mapear a `planner_request` y `advance_step`.
- Mantener solo fallback mínimo si judgement llega corrupto (sin reactivar lógica legacy).

4. `backend/negotiation/nodes/planner_node.py`
- Reescribir gate para que dependa de `planner_request + active_plan + advance_step`.
- Garantizar que `executor_instruction` siempre se genere, incluso en skip.

5. `backend/negotiation/progress_updater.py`
- Quitar cualquier write-back que resetee decisiones de control-flow.
- Mantener persistencia, outcomes y anti-loop orientado a plan runtime.

6. `backend/negotiation/nodes/progress_node.py`
- Ajustar merge/persistencia para respetar congelado de campos de decisión.

7. `backend/negotiation/elementos/render/executor_prompts.py`
- Reforzar instrucción de obediencia explícita a `executor_instruction`.

8. `backend/negotiation/validator.py` (o validador equivalente del executor)
- Añadir enforcement mínimo de contrato (`safe_mode`, `must_avoid`, `max_questions_per_turn`).

9. `backend/negotiation/schemas.py` y typed state en `backend/negotiation/negotiation_graph.py`
- Formalizar contrato v1 de judgement y señales (`planner_request`, `advance_step`, `active_plan`, `executor_instruction`).

## NO tocar
- `backend/negotiation/world_state_updater.py` (incluye `update_world_state(...)`).
- Prompt/estructura del extractor open-world.
- Lógica funcional de `belief_updater`.

---

## 3) Contrato final v1 de `policy_plan_judgement`

## Campos obligatorios
- `schema_version: "v1"`
- `turn_idx: int`
- `plan_presence: "active" | "none"`
- `plan_id: str` (vacío permitido si no hay plan)
- `evaluated_step_idx: int` (0 por defecto si no hay plan)
- `plan_status: "continue_same_step" | "advance_step" | "completed" | "interrupted_replan"`
- `why: str`
- `evidence: list[object]` (puede ser `[]` en degradado)
- `confidence: float` (0..1)
- `missing_signals: list[str]`
- `safety_flags: list[str]`
- `degraded: bool`
- `degrade_reason: str` (vacío si no degradado)

## Reglas de degradación (obligatorias)
1. Si LLM falla, timeout, error de red o parseo inválido:
   - devolver judgement **válido v1** con `degraded=true`.
2. Nunca devolver `None`.
3. Si no existe `active_plan`:
   - judgement válido con `plan_presence="none"`, `plan_status="interrupted_replan"`, `degraded=true|false` según resultado LLM, y razón explícita.
4. El pipeline no se interrumpe por fallo del judge.

---

## 4) Diseño de `world_judge_llm(...)`

## Inputs exactos
`world_judge_llm(...)` recibe:
- `active_plan` (dict | None)
- `current_step` (derivado de `active_plan.current_step_idx`, o `None`)
- `user_message` (texto del turno)
- `objective` (si disponible en state)
- `world_state_summary_short` (resumen corto no invasivo, opcional)
- `turn_count`
- `recent_history_snippet` (opcional acotado)

> Nota: no modifica ni depende del mecanismo open-world; solo consume estado ya producido.

## Salida exacta
- Objeto `policy_plan_judgement` v1 completo (campos obligatorios arriba).

## Estrategia de robustez
1. **Invocación principal LLM** con salida estructurada v1.
2. **Parseo estricto** (schema validation).
3. **1 retry acotado** si parseo inválido (re-prompt de reparación estructural).
4. Si sigue fallando:
   - fallback fail-safe degradado (válido v1),
   - `plan_status` conservador:
     - con plan: `continue_same_step` o `interrupted_replan` según seguridad mínima,
     - sin plan: `interrupted_replan`.
5. Registrar metadatos de fallo (`judge_error_type`, `judge_retry_count`, `degrade_reason`) sin romper turno.

---

## 5) Eliminación de dependencia de flags

## Flags que dejan de gobernar existencia del judge
- `WORLD_JUDGE_ENABLED` → eliminado para control funcional.
- `WORLD_JUDGE_NO_PLAN_AUTOFILL` → eliminado para control funcional.
- `WORLD_JUDGE_SHADOW` → no puede condicionar ejecución.

## Política final
- Judge siempre-on por defecto, sin feature flag de activación.
- Como mucho, flags de **logging/trace** (nivel de detalle), nunca de existencia/ejecución.

---

## 6) Matriz de precedencia de estado por turno (campos congelados)

| Fase | Puede escribir | Campos congelados tras fase |
|---|---|---|
| world_updater + world_judge_llm | `world_state`, `world_diff`, `policy_plan_judgement` | judgement congelado al salir de fase 1 |
| belief_updater | `belief_state`, `belief_update_meta` | judgement sigue congelado |
| policy_progress | `policy_state.planner_request`, `policy_state.advance_step`, `judgement_missing_streak` | `planner_request` + `advance_step` congelados |
| phase_policy_planner | `active_plan`, `active_plan_status`, `executor_instruction`, `policy_decision` | plan/instruction congelados |
| progress_updater | métricas, counters, loop flags, telemetría | **No puede tocar** judgement/request/advance_step/active_plan/current_step/executor_instruction |
| executor | `assistant_message`, `executor_output`, validator meta | no altera control-flow del turno |

Regla explícita: `progress_updater` solo puede emitir señales de seguridad para **próximo turno**, no reescribir decisiones ya tomadas en el turno actual.

---

## 7) Ajustes al resto del plan acordado

### A) `policy_progress` router mínimo (sin legacy)
- Switch puro por `plan_status`:
  - `continue_same_step` -> `continue_policy`, `advance_step=false`
  - `advance_step` -> `continue_policy`, `advance_step=true`
  - `completed` -> `replan_policy` (o `plan_completed` si se adopta ese estado)
  - `interrupted_replan` -> `replan_policy`
- Se elimina lógica legacy de attempts/slots/evaluate_step_success/phase recheck.

### B) `phase_policy_planner` gate definitivo
- Gate solo por `planner_request + active_plan + advance_step`.
- Skip planner únicamente cuando corresponde.
- Si `advance_step` y step queda fuera de rango => replan controlado.
- Siempre emitir `executor_instruction` derivada del step activo.

### C) `progress_updater` seguridad sin overwrite
- Persistencia y anti-loop adaptado:
  - `replan_churn` (cambios frecuentes de `plan_id` sin evidencia nueva),
  - `continue_loop` (muchos `continue_same_step` sin progreso),
  - señalización de salud para próximo turno.
- Sin reset de `planner_request` ni rehidratación destructiva de `policy_state`.

### D) `executor` en flujo LLM-first
- Mantener `strategy_summary` por compatibilidad, pero declarar precedencia:
  1) `executor_instruction` (autoritativa)
  2) constraints/validator
  3) strategy_summary como contexto secundario.
- Enforcement mínimo post-LLM:
  - verificar y reparar incumplimientos de `safe_mode`,
  - filtrar/evitar `must_avoid`,
  - respetar `max_questions_per_turn`.
- Si incumple: reparación mínima + traza `executor_instruction_compliance`.

---

## 8) Plan de migración por etapas (actualizado)

### Etapa 1 — Judge LLM siempre-on + contrato v1 estable
- Introducir `world_judge_llm(...)` separado, sin tocar world updater abierto.
- Producción obligatoria de judgement en 100% turnos (incluyendo degradado fail-safe).
- Router mínimo en paralelo (sin borrar todo legacy aún, pero sin usarlo para autoridad).

### Etapa 2 — Router minimal definitivo + gate planner contractual
- Eliminar lógica legacy de `policy_progress`.
- Mover autoridad final a `planner_request/advance_step/active_plan`.
- `phase_policy_planner` gobierna skip/advance/replan con contrato único.

### Etapa 3 — Harden persistencia + enforcement executor
- Blindar `progress_updater` contra overwrite de control-flow.
- Anti-loop nuevo operativo.
- Validator del executor hace cumplir contrato autoritativo de instrucción.

---

## 9) Tests unit/e2e a añadir o modificar

## Unit tests
1. `world_node`:
- cada turno genera `policy_plan_judgement` válido v1,
- si LLM falla/parsea mal => judgement degradado válido (nunca `None`),
- separación garantizada: no cambios de comportamiento en `update_world_state`.

2. `policy_progress`:
- mapping switch puro por `plan_status`,
- ausencia de rutas legacy (attempts/slots/success heuristics).

3. `planner_node`:
- matriz de gate:
  - continue + plan vigente => skip,
  - continue + advance_step => step++ sin LLM,
  - replan / no-plan / out-of-range => planner LLM.
- siempre emite `executor_instruction`.

4. `progress_updater`:
- no-overwrite de campos congelados del turno,
- anti-loop emite flags sin mutar decisión actual.

5. `executor/validator`:
- enforcement de `safe_mode`, `must_avoid`, `max_questions_per_turn`.

## E2E tests
1. Cobertura 100% judgement:
- en una simulación multi-turn, todos los turnos tienen judgement v1.

2. Resiliencia a fallo LLM judge:
- inyectar fallo de judge y verificar continuidad del pipeline con judgement degradado.

3. Flujo sin legacy:
- router/planner gate operan solo con `judgement + active_plan + advance_step`.

4. No churn / avance coherente:
- `plan_id` estable en `continue_same_step`,
- `current_step_idx` avanza solo con `advance_step`,
- replan solo en estados terminales/interrupción/out-of-range.

---

## 10) DoD verificable (runtime trace)
- [ ] 100% turnos con `policy_plan_judgement` v1 no nulo.
- [ ] `degraded=true` + `degrade_reason` presente cuando falla judge LLM.
- [ ] `planner_request` y `advance_step` coherentes con `plan_status`.
- [ ] `planner_skipped` coherente con gate contractual.
- [ ] `active_plan.current_step_idx` es la fuente de verdad del step runtime.
- [ ] `progress_updater` no reescribe campos congelados.
- [ ] `executor_instruction_compliance` trazado y reparaciones mínimas cuando aplica.

---

### Veredicto del plan actualizado v3
Este plan cumple la regla dura solicitada: **World Judge LLM siempre-on**, separado y aislado de `update_world_state(...)`, con salida `policy_plan_judgement` v1 **siempre válida** (incluyendo modo degradado fail-safe), y sin dependencia de flags para su existencia.
