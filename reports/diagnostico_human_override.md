# Diagnóstico técnico: “human override” vs pegado al plan

## 1) Mapa del pipeline real (turno de negociación)

Orden real del grafo (`StateGraph`):

1. `world_updater`
2. `belief_updater`
3. `policy_progress`
4. `phase_policy_planner`
5. `progress_updater`
6. `executor`

Fuente: wiring en `negotiation_graph.py` (`add_node` + `add_edge`).

### Paralelismo interno

Dentro de `world_updater` se puede lanzar en paralelo (threads):
- `world_judge_llm(...)`
- `build_advisor_recs(...)`

Luego se hace `flush_world_parallel_pending(...)` antes de `policy_progress` (vía `policy_progress_node`) para garantizar que `policy_plan_judgement` y `advisor_recs` estén consolidados en `state`.

---

## 2) Tabla global por componente (inputs/outputs/persistencia)

| Componente | Archivos/Fns | Inputs clave | Outputs clave | Persistencia |
|---|---|---|---|---|
| world_judge_llm | `backend/negotiation/nodes/world_node.py` → `world_judge_llm` | `active_plan`, `current_step`, `success_criteria`, `user_message`, `assistant_last_message`, `recent_history`, `memory_short/long`, `world_state_summary`, `progress_counters` | `policy_plan_judgement` con `plan_status`, `skip_planner`, `missing_signals`, `evidence`, `degraded`… + `judge_meta` | `state["policy_plan_judgement"]`, `state["extractor_meta"]["world_judge_meta"]`, `state["world_debug"]` y traza `debug_trace` |
| advisor_llm | `backend/negotiation/advisor.py` → `build_advisor_recs` (invocado desde `world_node.py`) | objetivo, historia, memoria, `active_plan`, `phase_state`, `policy_state`, `world_summary/full`, `belief_summary/full`, `progress_counters`, `speaker_of_last_message`, `last_counterparty_utterance` | `advisor_recs` normalizado (`diagnosis`, `recommended_moves`, etc.) + `advisor_meta` | `state["advisor_recs"]`, `state["advisor_meta"]` y `debug_trace` |
| policy_progress | `backend/negotiation/nodes/policy_progress_node.py` + `backend/negotiation/policy_progress.py` → `update_policy_state` | `policy_plan_judgement.plan_status`, estado previo de policy, retry guard | `policy_state.planner_request`, `advance_step`, `policy_meta` | `progress_state.policy_state`, `progress_state.advance_step`, `policy_meta` |
| planner gate + planner LLM | `backend/negotiation/nodes/planner_node.py` (`phase_policy_planner_node`) + `backend/negotiation/phase_policy_planner.py` (`plan_phase_policy`) | `planner_request`, `advance_step`, `judgement_skip_planner`, `active_plan`, retry guard, `advisor_recs`, `judge_result` | puede **omitir planner** y reutilizar plan; o llamar planner LLM y producir `active_plan`, `policy_decision`, opcional `executor_instruction` | `progress_state.active_plan`, `planner_meta`, `state.executor_instruction`, `policy_decision` |
| executor | `backend/negotiation/nodes/executor_node.py` + `backend/negotiation/executor/render_executor.py` | `strategy_summary.executor_instruction` (derivado del plan), `user_message`, memoria, world/belief, retry_hint | `executor_output` (`response_text`, `asked_question`, etc.) | `state.executor_output`, `assistant_message/response`; registra `asked_questions_recent` en `plan_ledger` |

---

## A) world_judge_llm

## A.1 Ubicación y prompt exacto

- Lógica principal: `backend/negotiation/nodes/world_node.py` (`world_judge_llm`).
- Prompt v2:
  - system: `WORLD_JUDGE_V2_SYSTEM_PROMPT`
  - user: `WORLD_JUDGE_V2_USER_PROMPT`
- Fuente de prompts: `backend/prompts.py` (reexportado por `backend/negotiation/repo_prompts.py`).

## A.2 Schema de salida observado

El contrato normalizado del judge (schema v1) incluye:
- `schema_version`
- `turn_idx`
- `plan_presence`
- `plan_id`
- `evaluated_step_idx`
- `plan_status` (`continue_same_step|advance_step|completed|interrupted_replan`)
- `why`
- `evidence[]`
- `confidence`
- `missing_signals[]`
- `safety_flags[]`
- `degraded`
- `degrade_reason`
- `skip_planner`

## A.3 Condiciones que llevan a `continue_same_step` vs `interrupted_replan`

### Lo que instruye el prompt
El system prompt v2 define `interrupted_replan` para:
- cambio de tema,
- bloqueo,
- nueva restricción fuerte,
- loop sin progreso repetido.

### Lo que fuerzan guardrails post-proceso
En `_post_normalize_evidence_guardrails(...)`:
- Si hay `continue_same_step` y `no_progress_same_step_turns >= 3`, se **convierte determinísticamente** a `interrupted_replan` con `degraded=true` y razón `loop_same_step_threshold`.
- Si `advance_step/completed` no trae evidence, se degrada a `continue_same_step`.

=> Esto hace que `interrupted_replan` hoy dependa fuerte de loop/counters, no necesariamente de una “desviación humana” de 1 turno.

## A.4 Guardrails deterministas sobre `skip_planner`

Sí, existe guardrail explícito:
- Si `plan_status in {"interrupted_replan","advance_step","completed"}` entonces `skip_planner=False` forzado en `_post_normalize_evidence_guardrails`.

Esto garantiza que en avance/replan/completed no se pueda saltar planner por salida del LLM.

## A.5 ¿Recibe current_step_micro_goal/success_criteria/active_plan/recent_history?

Sí:
- `active_plan` entra completo al payload/prompt.
- `current_step` se deriva de `active_plan.steps[current_step_idx]`.
- `success_criteria_list` se deriva del `current_step.success_criteria`.
- `recent_history` se inyecta (`recent_history_text` en prompt v2).

## A.6 Tabla pedida: inputs del judge

| input field | source | dónde se construye | dónde se usa |
|---|---|---|---|
| `active_plan` | `progress_state.active_plan` | `world_updater_node` llama `world_judge_llm(active_plan=...)` | prompt v2 (`active_plan_json`) + normalización | 
| `current_step` | derivado de `active_plan.current_step_idx` | dentro de `world_judge_llm` | prompt v2 (`current_step_json`) |
| `success_criteria_list` | `current_step.success_criteria` | dentro de `world_judge_llm` | prompt v2 (`success_criteria_json`) |
| `user_message` | turno actual | `run_negotiation_agent` → graph state | prompt + evidence |
| `assistant_last_message` | historial previo | `_last_assistant_message(state.history)` | prompt + evidence |
| `recent_history` | snippet conversación | `build_context_snippet(...)` en graph state | prompt + evidence |
| `memory_short/long` | memoria del turno | `build_memory_context(...)` | prompt |
| `world_state_summary/digest` | `world_state` (+`world_diff`) | `world_judge_llm` | prompt |
| `progress_counters` | `progress_state` | `world_judge_llm` | prompt y guardrails (`no_progress_same_step_turns`) |

---

## B) advisor_llm

## B.1 Dónde se llama, cuándo se ejecuta, y flush paralelo

- Se invoca desde `world_updater_node` (`_run_advisor` -> `build_advisor_recs`).
- Si `WORLD_PARALLELISM_ENABLED=1`, advisor y judge se lanzan en paralelo; resultados quedan en `_pending_world_parallel`.
- El `flush` ocurre en `policy_progress_node` mediante `flush_world_parallel_pending(state)` antes de decidir `planner_request`.

## B.2 ¿Planner recibe advisor siempre?

- En `phase_policy_planner_node`, cuando **sí llama** planner LLM (`not planner_skipped`), pasa `advisor_recs` a `plan_phase_policy(...)`.
- Si planner está **skipped** por gate (`continue_same_step_without_planner`, `judge_skip_planner`, `advance_step_without_planner`), las recomendaciones del advisor **no influyen** en esa vuelta de planner.

## B.3 ¿Executor recibe advisor directamente?

No directo.
- El executor no consume `advisor_recs` explícitamente.
- Le llega indirectamente si planner las materializa en `active_plan`/`executor_instruction`.
- Si planner se salta, executor opera con instruction heredada del plan actual.

## B.4 Diagrama flujo advisor → planner/executor

`world_updater` → `advisor_recs/advisor_meta` en `state`  
`policy_progress` (solo planner_request desde judge; advisor no gatea aquí)  
`phase_policy_planner_node`:
- camino A (skip): no planner LLM, no uso advisor
- camino B (execute): `plan_phase_policy(... advisor_recs=state["advisor_recs"])`  
`executor`: usa `state["executor_instruction"]` (derivado de plan), no `advisor_recs`.

Campos state relevantes:
- `state.advisor_recs`, `state.advisor_meta`
- `state.progress_state.policy_state.planner_request`
- `state.executor_instruction`

---

## C) phase_policy_planner / planner_node

## C.1 Gate principal continue vs replan

Se decide en dos capas:

1) `policy_progress.update_policy_state` traduce `plan_status` → `planner_request`:
- `continue_same_step` → normalmente `continue_policy` (o `replan_policy` según flags/estado)
- `advance_step` → `continue_policy` + `advance_step=True`
- `completed`/`interrupted_replan` → `replan_policy`

2) `phase_policy_planner_node` aplica gate final:
- Si `planner_request=continue_policy` y plan válido, hay múltiples rutas de **skip planner**.
- Solo en rutas no-skipped invoca `plan_phase_policy` (LLM planner).

## C.2 Rutas que causan “seguir sin pensar”

En `phase_policy_planner_node`:
- `skip_reason="judge_skip_planner"` cuando `judgement_skip_planner=True`.
- `skip_reason="continue_same_step_without_planner"` cuando reutiliza policy/plan del step actual.
- `skip_reason="advance_step_without_planner"` al avanzar step localmente sin LLM.

Estas rutas reutilizan `previous_plan` y derivan `executor_instruction` desde step vigente (`_build_executor_instruction`).

## C.3 Influencia de `planner_request`

`planner_request` viene de `policy_state` (construido en `policy_progress`). Es el disparador primario del gate.
Si llega `continue_policy`, la ruta por defecto favorece reutilización/skip salvo bloqueos (`retry_guard`, out-of-range, fin de plan, etc.).

## C.4 Construcción de `executor_instruction`

- Camino normal skip o fallback: `_build_executor_instruction(active_plan)` usa:
  - `step_micro_goal` <- `step.micro_goal`
  - `instruction` <- `step.what_to_do`
  - `ask` <- `step.ask`
  - `safe_mode`, `must_avoid`, `max_questions_per_turn` <- `plan_constraints`
- Camino planner v2: si `planner_meta.executor_instruction` existe, lo usa directo.

## C.5 Viabilidad para introducir luego “human_mode / common sense overrides”

Sin proponer implementación aún, puntos viables existentes:
- **Input planner**: `plan_phase_policy(...)` ya recibe `judge_result`, `advisor_recs`, `pivot_required`; podría ampliarse con flag adicional.
- **Prompt planner**: `PLANNER_V2_SYSTEM_PROMPT` + `PLANNER_V2_USER_PROMPT` ya tienen bloques para reglas duras y campos JSON (lugar natural para `human_mode`).
- **Plumbing gate**: `phase_policy_planner_node` es el punto donde se decide skip vs invoke y donde podría leerse un override consolidado.

## C.6 ¿Schema de plan soporta campos extra por step?

No en salida directa del planner v2:
- `PlannerV2StepModel`, `PlannerV2ActivePlanModel`, `PlannerV2DecisionModel` usan `extra="forbid"`.

Además, `_to_active_plan(...)` mapea explícitamente campos permitidos y descarta extras.

En cambio, `progress_state.active_plan` (como dict en runtime) no se normaliza estrictamente en `normalize_progress_state`, pero el contrato de planner LLM sí es estricto.

## C.7 Lista exacta de funciones/archivos (touch points planner)

- Prompt planner:
  - `backend/prompts.py` (`PLANNER_V2_SYSTEM_PROMPT`, `PLANNER_V2_USER_PROMPT`)
- Parsing/validación planner:
  - `backend/negotiation/elementos/strategy_definitions.py` (`PlannerV2*Model`)
  - `backend/negotiation/phase_policy_planner.py` (`with_structured_output(PlannerV2DecisionModel)`, `_to_active_plan`)
- Gate logic planner node:
  - `backend/negotiation/nodes/planner_node.py` (`phase_policy_planner_node`)

---

## D) executor_node / render_executor

## D.1 Contract executor input → output

### Input efectivo
`render_executor_output(...)` recibe:
- `strategy_summary.executor_instruction` (que encapsula plan/step)
- `user_message`, `memory_short/long`, `world_json`, `belief_json`, `retry_hint`, speaker.

Prompt executor (user template) incluye bloque:
- `INSTRUCCION_DEL_PLANNER (PRIORIDAD MAXIMA)` con `executor_instruction_json`.

### Output esperado
JSON `executor_v2`:
- `response_text`
- `asked_question` (bool)
- `requested_info_slots` (list)
- `tone_used`
- `followup_intent`
- `render_meta`

## D.2 ¿Tiene libertad para salirse del “ask del plan”?

Muy limitada por prompt + post-validaciones:

1) Prompt: declara prioridad máxima de instrucción planner.
2) `_instruction_followed(...)` valida:
- si instruction sugiere preguntar y falta `?` => incumplimiento
- si `executor_instruction.ask` existe y su texto no aparece en respuesta (match substring) => incumplimiento (`missing_required_ask_slot`)
3) Si incumple y no hay pregunta, fuerza `?` automáticamente.

=> El sistema empuja al executor a sostener la pregunta del plan incluso ante desvíos humanos.

## D.3 ¿Lugar claro para inyectar “respuesta humana primero” sin replan?

Puntos naturales existentes (sin proponer cambio aún):
- Prompt executor (`EXECUTOR_V2_SYSTEM_PROMPT` / `EXECUTOR_V2_USER_PROMPT`).
- Pre-shaping en `render_executor_output(...)` antes del invoke (ya arma `retry_hint`, `planner_output_summary`, etc.).
- Post-checks en `executor_node` (`_instruction_followed`, `_enforce_executor_instruction`) son donde hoy se bloquea conducta flexible.

## D.4 Registro de pregunta real ejecutada

Sí:
- `_register_recent_question(...)` (en executor node) extrae la última pregunta de `response_text` y actualiza `progress_state.plan_ledger.asked_questions_recent`.
- También `progress_updater._record_recent_question(...)` puede reforzar registro.

## D.5 Validaciones que pueden bloquear conducta human-first

- `missing_required_ask_slot` exige incluir token de `executor_instruction.ask`.
- `expects_question` en `_instruction_followed` exige pregunta si instruction lo sugiere.
- `max_questions_per_turn` recorta preguntas extras.

Estas validaciones favorecen “pregunta del step” por encima de respuesta social/side-quest.

---

## E) policy_progress_node

## E.1 Traducción `plan_status` → `planner_request`

En `update_policy_state(...)`:
- `continue_same_step` → `continue_policy` (salvo condiciones de forzado a replan)
- `advance_step` → `continue_policy` + `advance_step=True`
- `completed` o `interrupted_replan` → `replan_policy`

## E.2 ¿Existe paso obligatorio por advisor?

No.
Advisor corre en world_updater, pero `policy_progress` no condiciona planner_request a advisor. Tampoco hay “must consult advisor before continue”.

## E.3 Punto exacto para forzar replan por cambio de objetivo explícito

El punto de control actual es `update_policy_state(...)`, rama donde consume `status` proveniente de `policy_plan_judgement.plan_status`.
Si judge marca `interrupted_replan`, ya fuerza `planner_request="replan_policy"`.

---

## 3) Simulación por lectura (sin ejecutar LLM real)

## Caso 1: usuario hace pregunta personal (“cómo estás”, “cuéntame de ti”)

Flujo probable actual:
1. Judge puede marcar `continue_same_step` (si no detecta cambio de objetivo fuerte).
2. `policy_progress` traduce a `continue_policy`.
3. `planner_node` toma ruta skip (`judge_skip_planner` o `continue_same_step_without_planner`) y mantiene plan/step.
4. Executor recibe misma instrucción del plan y, por `_instruction_followed`, intenta mantener pregunta del step.

Resultado: respuesta tiende a volver rápido al ask de negociación, con tono robotizado.

Dónde se decide:
- Gate principal en `planner_node` (skip planner bajo continue).
- Compliance en `executor_node` obliga pregunta/ask del step.

## Caso 2: usuario hace aclaración/historia lateral

Flujo probable:
1. Judge muchas veces mantiene `continue_same_step` hasta acumular evidencia de loop.
2. `no_progress_same_step_turns` sube en `progress_updater`.
3. Mientras no llegue umbral, planner sigue en modo continue/skip, executor insiste en el mismo carril.

Solo al umbral (`>=3`) un guardrail del judge transforma a `interrupted_replan`.

## Caso 3: usuario cambia objetivo explícitamente

Ruta esperada correcta:
1. Judge detecta cambio de objetivo y emite `interrupted_replan`.
2. Guardrail fuerza `skip_planner=false` para ese status.
3. `policy_progress` pone `planner_request=replan_policy`.
4. `planner_node` ejecuta planner LLM (no skip), regenera plan/instrucción.

Riesgo actual observado por lectura:
- Si judge no clasifica ese texto como `interrupted_replan` (queda en `continue_same_step`), el gate posterior favorece continuidad por skip/reuse.

---

## 4) Root causes del “pegado al plan”

1. **Sesgo estructural a `continue_policy + skip`**: cuando judge devuelve `continue_same_step`, planner puede saltarse totalmente y reutilizar plan/step.
2. **Executor con compliance rígida al ask**: `_instruction_followed` y enforcement posterior penalizan respuestas que no contengan la pregunta esperada.
3. **Advisor no tiene canal directo al executor**: si planner se omite, advisor no modifica comportamiento conversacional ese turno.
4. **Replan por desvío humano depende demasiado del judge**: sin `interrupted_replan`, el resto del pipeline asume continuidad.
5. **Umbral de loop tardío** (`>=3`) para escalar a `interrupted_replan`: side-quests de 1 turno quedan absorbidas como “seguir igual”.

---

## 5) Touch points priorizados (para implementar después)

> Solo listado técnico de puntos de intervención existentes.

1. **Executor common-sense override (human-first)**
   - `backend/negotiation/elementos/render/executor_prompts.py`
   - `backend/negotiation/executor/render_executor.py`
   - `backend/negotiation/nodes/executor_node.py` (especialmente `_instruction_followed` / enforcement)

2. **Advisor recommendations con señal de “human_mode”**
   - `backend/prompts.py` (`ADVISOR_V2_*`)
   - `backend/negotiation/advisor.py` (normalización/salida)
   - Plumbing de consumo en `backend/negotiation/nodes/planner_node.py`

3. **Planner prompt para incorporar `human_mode`**
   - `backend/prompts.py` (`PLANNER_V2_SYSTEM_PROMPT`, `PLANNER_V2_USER_PROMPT`)
   - `backend/negotiation/phase_policy_planner.py` (format_messages + payload)
   - Si se requieren nuevos campos estructurados: `backend/negotiation/elementos/strategy_definitions.py`

4. **Judge para `interrupted_replan` en cambio explícito de objetivo**
   - `backend/prompts.py` (`WORLD_JUDGE_V2_SYSTEM_PROMPT`, `WORLD_JUDGE_V2_USER_PROMPT`)
   - `backend/negotiation/nodes/world_node.py` (`world_judge_llm`, `_post_normalize_evidence_guardrails`)

---

## 6) Lista mínima de tests a añadir (solo diseño)

1. **Human-first + puente + retoma (sin replan obligatorio)**
   - Dado un step activo de negociación y user message social/personal,
   - verificar que respuesta puede contener micro-respuesta humana + puente + pregunta del step,
   - y que no rompe constraints ni asked_question contract.

2. **Replan obligatorio ante cambio explícito de objetivo**
   - Dado mensaje tipo “quiero hablar de otro objetivo distinto”,
   - judge => `interrupted_replan`, `skip_planner=false`,
   - policy_progress => `planner_request=replan_policy`,
   - planner_node no debe tomar ruta skip.

3. **Side-quest de 1 turno no degrada a robot**
   - Dado desvío lateral corto,
   - validar que executor no repite mecánicamente la misma pregunta,
   - y retoma negociación sin colapsar a replan innecesario.

## Comandos sugeridos de validación

- `pytest backend/tests/test_policy_progress_invariants.py -q`
- `pytest backend/tests/test_executor_plan_compliance.py -q`
- `pytest backend/tests/test_judge_advisor_v2_prompts.py -q`
- `pytest backend/tests/test_phase_policy_prompt_format.py -q`
- `pytest backend/tests/test_e2e_negotiation_pipeline.py -q -k "judge or advisor or planner or executor"`

