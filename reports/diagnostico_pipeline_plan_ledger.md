# Diagnóstico técnico del runtime actual (world/judge/planner/executor/progress/memory)

## Alcance y método
- Se revisó el pipeline real en `backend/negotiation/negotiation_graph.py` y los nodos conectados.
- Se trazaron contratos de datos en funciones núcleo: world extractor/judge, planner, progress updater, executor, memoria.
- Se buscó evidencia puntual de los síntomas reportados (literalidad del judge, repetición del planner/executor, drift de estado).

---

## A) Pipeline real actual (orden, dependencias, paralelismo)

### Grafo de ejecución real (LangGraph)
Orden **secuencial** del grafo:
1. `world_updater`
2. `belief_updater`
3. `policy_progress`
4. `phase_policy_planner`
5. `progress_updater`
6. `executor`

Definido en `StateGraph` con edges lineales desde `START` hasta `END`.

### Paralelismo efectivo
- El grafo es secuencial a nivel de nodos.
- Dentro de `world_updater_node`, existe paralelismo interno opcional (`WORLD_PARALLELISM_ENABLED`) para ejecutar en paralelo:
  - extracción world,
  - world_judge,
  - advisor.
- El resultado de judge/advisor puede quedar pendiente y se hace `flush` al entrar en `policy_progress_node` (`flush_world_parallel_pending`).

### Flujo de datos de alto nivel
- `run_negotiation_agent` construye `graph_state` con historial, memoria, world/belief/progress normalizados y metadatos.
- Tras `negotiation_app.invoke(graph_state)`, persiste en `SessionState`:
  - `world_state`, `belief_state`, `progress_state`, `last_policy_executed`, `history`, `debug_trace`.

---

## B) Contrato de datos actual por componente

## 1) world_extractor_llm + merge world

### Ubicación
- `backend/negotiation/world_state_updater.py`
  - `update_world_state(...)`
  - `merge_world_buckets_append_mostly(...)`
- `backend/negotiation/extractors/world_extractor_v4.py`
  - `extract_world_patch_llm_v4(...)`

### Input real
`extract_world_patch_llm_v4` recibe:
- `user_message`, `prev_world_state`, `conversation_mode`, `turn_idx`.
- contexto de planificación: `last_assistant_question`, `current_step_micro_goal`, `success_criteria`, `missing_signals`, `expected_slots`.
- bloque de contexto público/background.

`update_world_state` recibe además `belief_state`, `deps`, y perfiles de render para construir prompt/contexto.

### Output real
- Patch normalizado por buckets: `offers/concessions/constraints/interests/claims/requests/context`.
- `meta` extractor (latencia, tokens, dedupe, contradicciones, etc.).
- `update_world_state` devuelve `(world_state_nuevo, extractor_meta)`; luego en `world_node` se calcula `world_diff`.

### Persistencia en estado
- `state["world_state"]`
- `state["world_diff"]`
- `state["extractor_meta"]`
- luego persiste a `SessionState.world_state` al final del turno.

## 2) world_judge_llm (prompt + normalización + guardrails + skip_planner)

### Ubicación
- `backend/negotiation/nodes/world_node.py`
  - `world_judge_llm(...)`
  - `_normalize_judgement(...)`
  - `_post_normalize_evidence_guardrails(...)`
- Prompt:
  - `backend/prompts.py` (`WORLD_JUDGE_V2_SYSTEM_PROMPT`, `WORLD_JUDGE_V2_USER_PROMPT`)

### Input real
- `active_plan` completo y `current_step` derivado por `current_step_idx`.
- `success_criteria_json` del step actual.
- `user_message`, `assistant_last_message`, `recent_history`, `memory_short`, `memory_long`.
- `world_state` (digest + full compacto), `progress_counters` y `evidence_candidates`.

### Output real (schema v1)
Campos clave:
- `plan_status ∈ {continue_same_step, advance_step, completed, interrupted_replan}`
- `why`, `evidence[]`, `missing_signals[]`, `skip_planner`, `degraded`, etc.

### Guardrails/post-proceso reales
- Si `advance_step/completed` sin `evidence`, se degrada a `continue_same_step`.
- Si faltan evidencias pero hay texto, inyecta evidencia candidata.
- Si `no_progress_same_step_turns >= 3` y status sigue `continue_same_step`, fuerza `interrupted_replan`.
- **No existe guardrail que fuerce `skip_planner=false` cuando `plan_status=advance_step`**; eso hoy queda a lo que devuelva el LLM (el prompt lo recomienda, pero no hay hard-guard en postproceso para esa combinación).

### Persistencia
- `state["policy_plan_judgement"]`
- `state["extractor_meta"]["world_judge_meta"]`
- `state["world_debug"]["policy_plan_judgement"]`

## 3) planner (generación de plan, schema de steps, success_criteria, replan)

### Ubicación
- Nodo: `backend/negotiation/nodes/planner_node.py` (`phase_policy_planner_node`).
- LLM planner: `backend/negotiation/phase_policy_planner.py` (`plan_phase_policy`).
- Prompt planner: `backend/prompts.py` (`PLANNER_V2_SYSTEM_PROMPT`, `PLANNER_V2_USER_PROMPT`).

### Input real al planner LLM
- `world_state`, `world_diff`, `belief_state`.
- `progress_state`, `policy_state`, `active_plan_prev`, `phase_state_prev`.
- `judge_result`, `advisor_recs`, `objective`, `constraints`.
- `memory_short`, `memory_long`.
- `allowed_policy_ids`.

### Output real
- `phase_candidate`, `policy_decision`, `planner_meta`.
- `planner_meta` puede incluir `active_plan` (si LLM v2 lo devuelve);
  si no, se construye plan fallback `_build_active_plan_from_replan(...)`.

### Schema de `active_plan` usado runtime
- `plan_id`, `current_step_idx`, `steps[]`.
- Step típico: `step_idx`, `micro_goal`, `what_to_do`, `ask`, `success_criteria`, `replan_triggers`, `safe_mode`.

### Lógica de replan/advance
- Si `planner_request=continue_policy` y `advance_step=True`, intenta `_advance_step` local sin llamar LLM.
- Si llegó al último step o no se puede avanzar, fuerza `replan_policy`.
- Si `judgement_skip_planner=True`, puede saltarse planner y mantener plan/policy.

### Persistencia
- `state["progress_state"]["active_plan"]`, `active_plan_status`, `phase_state`.
- `state["policy_decision"]`, `state["executor_instruction"]`, `state["planner_meta"]`.

## 4) progress_updater (persistencia de active_plan/current_step/no_progress/loop)

### Ubicación
- `backend/negotiation/nodes/progress_node.py`
- `backend/negotiation/progress_updater.py` (`update_progress_state`)

### Input real
- `prev_progress`, `policy_decision`, `last_policy_executed`, `prev_world_state`, `world_state`, `prev_belief_state`, `belief_state`, `turn_count`.

### Output real
- `progress_state` actualizado con:
  - `policy_attempts`, `last_executed_policy_*`, `last_chosen_policy_id`.
  - `turns_in_same_mode`, `plan_id_changes_window`, `last_plan_id`.
  - `no_progress_same_step_turns` (derivado de `last_judgement_status`).
  - `loop_flags` (`continue_loop`, `replan_churn`, `stuck_in_policy`).
- **No mantiene historial de intents resueltos/fallidos, ni ledger de preguntas/attempts por intent.**

### Persistencia
- `state["progress_state"]` y luego `SessionState.progress_state`.

## 5) executor (qué decide preguntar/decir y uso world/belief/memory)

### Ubicación
- `backend/negotiation/nodes/executor_node.py` (`executor_node`).
- Render LLM: `backend/negotiation/executor/render_executor.py` (`render_executor_output`).

### Input real
- `policy_decision`/`executed_policy`.
- `strategy_summary` (incluye `executor_instruction`: plan_id, step_idx, instruction, ask, etc.).
- `world_state` completo.
- `belief_state` completo (y resumen compactado auxiliar).
- `memory_short`, `memory_long`, `user_message`.

### Output real
- `executor_output` normalizado (`response_text`, `asked_question`, `requested_info_slots`, `followup_intent`, etc.).
- `assistant_message` / `response`.
- metadatos de validación y trazas.

### Nota operativa
- El prompt sí recibe `executor_instruction_json` y `planner_output_summary` con `plan_id`.
- Pero no hay un guard hard que compare "pregunta nueva" contra un historial de preguntas hechas por intent; solo hints de retry (`_build_retry_hint`) y validaciones de formato/seguridad.

## 6) Memoria short/long

### Ubicación
- `backend/negotiation/context_utils.py`
  - `build_memory_context(...)`
  - `maybe_refresh_summary(...)`
- Orquestación: `backend/negotiation/negotiation_graph.py` (`run_negotiation_agent`).

### Input/Output real
- Entrada: `SessionState.history` + `SessionState.summary`.
- Salida:
  - `long_memory` = summary JSON limpio (si válido).
  - `short_memory` = últimos N turnos usuario/assistant en texto.
  - `memory_meta`.
- Se inyectan a world_judge, planner y executor en cada turno.

### Persistencia
- `summary` y `history` viven en `SessionState`.
- `refresh_meta` y `memory_meta` van a trace/debug del turno.

---

## C) Diagnóstico de síntomas con evidencia del comportamiento actual

## 1) ¿success_criteria se trata como AND estricto?
- No hay implementación determinística tipo AND en código procedural.
- La decisión de cumplimiento se delega al LLM del judge vía prompt (“hay evidencia explícita de cumplir success_criteria”).
- El backend solo valida evidencia mínima/consistencia de forma superficial.

**Conclusión**: hoy no existe motor explícito de matching por intención ni por lógica booleana formal; depende de interpretación del LLM + guardrails básicos.

## 2) ¿Judge literal vs intención?
- El judge recibe `success_criteria_json` y decide `plan_status` por evidencia textual.
- No hay capa semántica adicional en backend (embeddings/rules/intents) para mapear “respuesta equivalente” a criterio cumplido.
- Esto explica casos donde una respuesta parafraseada puede no disparar `advance_step`.

## 3) ¿Validador que fuerce skip_planner=false cuando advance_step?
- No se encontró hard-guard de esa forma.
- Hay regla en prompt que lo sugiere, pero post-proceso no corrige inconsistencia `advance_step + skip_planner=true`.

## 4) ¿Por qué planner puede repetir objetivos?
- No existe lista persistente de “objetivos/intents resueltos” en `progress_state`.
- Tampoco hay `plan_ledger` (resolved/open/failed + attempts + asked_questions).
- El estado de completitud de steps se reduce a `current_step_idx` del plan activo; al replan, el plan puede recrear micro-goals semánticamente repetidos.
- El planner sí ve world/belief/memory completos, pero sin estructura explícita anti-repetición persistente de intents.

## 5) ¿Por qué executor repite preguntas?
- Executor sí consume world/belief/memory y `executor_instruction`.
- Pero no hay memoria estructurada de “preguntas ya hechas por intent/step” ni control de retries por intent.
- `_build_retry_hint` usa señales de no progreso, pero no bloquea repetición semántica de pregunta.

## 6) ¿Drift de estado posible?
- `current_step_json` puede quedar vacío si no hay `active_plan` válido o `steps` inválidos/out-of-range (se pasa `{}` al prompt).
- `plan_id` puede cambiar por replans y solo se trackea ventana (`plan_id_changes_window`) sin ledger histórico completo.
- `progress_state.get("progress_counters", {})` se envía al planner, pero ese objeto no se ve poblado sistemáticamente por `update_progress_state`; riesgo de contexto incompleto para anti-loop.
- Judge/advisor pueden ejecutarse en paralelo con `prev_world`; luego se marca posible staleness (`judge_may_be_stale_due_to_world_update`).

---

## D) Puntos exactos de cambio para implementación futura (sin implementar)

## 1) Advance por intención (judge + estilo success criteria)

### Archivo candidato 1
`backend/negotiation/nodes/world_node.py`
- Funciones: `world_judge_llm`, `_post_normalize_evidence_guardrails`, `_normalize_judgement`.
- Cambios futuros esperados:
  - nuevo campo en judgement normalizado: p.ej. `intent_match` / `matched_criteria`.
  - hard-guard de consistencia (`advance_step => skip_planner=False`).
  - validación semántica adicional antes de confirmar avance.

### Archivo candidato 2
`backend/prompts.py`
- Prompt `WORLD_JUDGE_V2_*`.
- Cambios futuros:
  - instruir evaluación por intención/equivalencia semántica vs match literal.
  - salida estructurada con trazabilidad de criterio/intención cumplida.

## 2) Plan Ledger persistente en progress_state

### Archivo candidato 3
`backend/negotiation/schemas.py`
- `ProgressState` + `default_progress_state`.
- Añadir campo nuevo compatible: `plan_ledger` con subestructuras `resolved/open/failed`, `attempts`, `asked_questions`, timestamps/turnos.
- Compatibilidad: default vacío para no romper tests/migraciones.

### Archivo candidato 4
`backend/negotiation/progress_updater.py`
- `update_progress_state`.
- Actualizar ledger por turno usando `policy_plan_judgement`, `executor_output`, `active_plan`.
- Mantener backward compatibility (si falta ledger, inicializar on-the-fly).

## 3) Anti-repetición en planner + retries por intent

### Archivo candidato 5
`backend/negotiation/phase_policy_planner.py`
- `plan_phase_policy` + normalización de `active_plan`.
- Inyectar `plan_ledger` en prompt/input y validar que nuevos steps no reabran intents resueltos.
- Control de max intentos por intent/step (p.ej. 2) para forzar replan/pivot.

### Archivo candidato 6
`backend/negotiation/nodes/planner_node.py`
- `phase_policy_planner_node` (gate de `advance_step`, `judgement_skip_planner`, `_advance_step`).
- Aplicar reglas determinísticas de retry threshold/forzado a replan según ledger.
- Asegurar que `executor_instruction` y `active_plan` se mantengan consistentes.

(Complementario opcional: `backend/negotiation/executor/render_executor.py` para registrar `asked_questions` por intent en runtime y alimentar ledger.)

---

## Checklist solicitado

### Pipeline real + paralelismo
- ✅ Mapeado: grafo secuencial + paralelismo interno en world_updater.

### Tabla componente→archivo→input→output→estado
- ✅ Incluida arriba para world_extractor, world_judge, planner, progress_updater, executor, memoria.

### Confirmaciones clave
- ✅ `advance/continue/interrupted`: decidido por `policy_plan_judgement.plan_status` y propagado a `policy_state.planner_request` + `progress_state.advance_step`.
- ✅ `skip_planner`: llega desde judge; planner node lo usa como gate para saltarse LLM en `continue_policy`.
- ✅ Repetición: no hay ledger persistente ni historial formal de intents/preguntas.

### Puntos de intervención priorizados
- ✅ 6 archivos priorizados con función y tipo de campo/cambio esperado.

### Recomendaciones de tests (sin implementarlos aún)
1. Test de consistencia judge:
   - caso `plan_status=advance_step` => debe salir `skip_planner=false` (hard invariant).
2. Test de equivalencia semántica:
   - paraphrase/intent match de success criteria debe permitir avanzar.
3. Test de ledger persistente:
   - `progress_state.plan_ledger` inicializa vacío y persiste entre turnos.
4. Test anti-repetición planner:
   - intent resuelto no reaparece en nuevo `active_plan`.
5. Test retries:
   - al intento 3 de mismo intent/step, fuerza replan/pivot.
6. Test executor no-reask:
   - con `asked_questions` previas en ledger, evita repetir misma pregunta semántica.
7. Test de compatibilidad/migración:
   - estados legacy sin `plan_ledger` no rompen pipeline ni tests existentes.
