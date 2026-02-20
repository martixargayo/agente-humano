# Informe técnico: PHASE_POLICY_PLANNER y gate de skip

## 1) MAPA DE ARCHIVOS (source of truth)

- `backend/negotiation/negotiation_graph.py`: define el pipeline fijo de nodos (`START -> world_updater -> belief_updater -> policy_progress -> phase_policy_planner -> progress_updater -> executor -> END`) y la instrumentación de timing/skipped por nodo.
- `backend/negotiation/nodes/planner_node.py`: implementación del nodo `phase_policy_planner_node`; contiene el gate real de skip (inline), llamada al planner LLM, fallback, normalización, `planner_meta`, `planner_debug`, `gate_meta`.
- `backend/negotiation/phase_policy_planner.py`: función `plan_phase_policy`, construcción de prompt `system+user`, llamada `get_planner_llm().with_structured_output(...)`, parseo/normalización y fallback por excepción.
- `backend/prompts.py`: texto literal de `PHASE_POLICY_SYSTEM_PROMPT` y `PHASE_POLICY_USER_PROMPT` usados por planner.
- `backend/negotiation/nodes/policy_progress_node.py`: puente entre `policy_plan_judgement` y `update_policy_state`; persiste `last_judgement_status`, `judgement_missing_streak`.
- `backend/negotiation/policy_progress.py`: mapeo `plan_status -> planner_request` y `progress_state["advance_step"]`.
- `backend/negotiation/nodes/world_node.py`: produce `policy_plan_judgement` vía `world_judge_llm` (incluye `skip_planner`, `plan_status`, `evidence`, `degraded`).
- `backend/negotiation/policy_planner.py`: calcula `allowed_policy_ids` / `allowed_policy_ids_with_reasons` según fase, recovery, required inputs/beliefs, constraints.
- `backend/negotiation/phase_state_updater.py`: posprocesa `phase_candidate` del planner (hysteresis, recovery mode, gate de fase efectiva).
- `backend/negotiation/validation.py`: `normalize_policy_decision` (allowlist de policy_id, truncados, issues).
- `backend/negotiation/llm_clients.py`: `get_planner_llm`.
- `backend/negotiation/config/models.py`: defaults de modelo/timeout/max_tokens/retries y kwargs efectivos de `ChatOpenAI`.
- `backend/negotiation/telemetry/trace_runtime.py`: runtime de timing por nodo y `llm_calls`.
- `backend/negotiation/telemetry/live_trace.py`: serialización final de evento de LiveTrace (`planner_meta`, `planner_debug`, `gates`, `timing`, `llm_calls`).
- `backend/negotiation/gating/gate_planner.py`: existe una función de gating de planner (`gate_phase_policy`) **pero no está conectada** al nodo planner actual.
- `backend/tests/test_policy_progress_and_planner_invariants.py`: invariantes de skip/call planner + mapeo completed->replan.
- `backend/tests/test_phase_policy_prompt_format.py`: robustez de plantilla prompt y fallback por `prompt_format`.
- `backend/tests/test_live_trace_runtime_wiring.py`: wiring de `timing.nodes` y `llm_calls` para planner.

## 2) FLOW END-TO-END (secuencia exacta)

### Entrypoint y orden literal
1. `policy_progress_node(state)` toma `policy_plan_judgement`, actualiza `progress_state.last_judgement_status`, llama `update_policy_state(...)` y escribe `policy_state.planner_request` + `progress_state.advance_step`.
2. `phase_policy_planner_node(state)` lee `progress_state`, `policy_plan_judgement`, calcula `allowed_policy_ids`, decide si skippea o llama planner.
3. Si llama planner: `deps.plan_phase_policy(...)` (por defecto `plan_phase_policy`) devuelve `(phase_candidate, policy_decision, planner_call_meta)`.
4. `postprocess_phase_candidate(...)` transforma candidato de fase a `phase_effective` (hysteresis/recovery).
5. `normalize_policy_decision(...)` valida/ajusta `policy_decision` contra `allowed_policy_ids`.
6. Construye/reutiliza `active_plan` y `executor_instruction`.
7. Escribe `planner_meta`, `planner_debug`, `gate_meta`.
8. `progress_updater_node` consume `policy_decision`+estado y actualiza contadores anti-loop.
9. `executor_node` usa `policy_decision` y `executor_instruction` para generar respuesta final.

### Campos que lee `phase_policy_planner_node`
- `progress_state.policy_state.planner_request`
- `progress_state.advance_step`
- `progress_state.active_plan`
- `policy_plan_judgement.skip_planner`
- `world_state`, `belief_state`, `world_diff`, `objective`, `constraints`, `hard_constraints_struct`, `recent_history_text`

### Campos que escribe
- `state.allowed_policy_ids`
- `state.phase_candidate`
- `state.phase_effective`
- `state.policy_pre_repair` (actualmente `None`)
- `state.policy_post_repair`
- `state.policy_decision`
- `state.planner_meta`
- `state.planner_debug` y `state.planner_debug_v2`
- `state.executor_instruction`
- `state.gate_meta` (`planner_skipped`, `skip_reasons.planner`)
- `state.progress_state` (actualiza `active_plan`, `active_plan_status`, `advance_step=False`, gate counters)

### Diagrama breve
`policy_progress(plan_status->planner_request/advance_step)` -> `planner_node(gate inline skip?)` -> (`skip`: reuse/advance plan) **o** (`execute`: planner_llm + normalize + build plan) -> `policy_decision` -> `executor`

### Fallos y fallback
- Si `deps.plan_phase_policy` lanza excepción en `planner_node`: marca `planner_failed=True`, `planner_fallback_used=True`, `policy_decision=default_policy_decision()`, `phase_candidate` fallback climate/conf 0.
- Si falla dentro de `plan_phase_policy`: retorna fallback seguro `_fallback_policy(allowed_policy_ids)` + meta con `planner_error_stage` (`prompt_format` o `llm_invoke`).

## 3) GATE DE SKIP DEL PLANNER (crítico)

### ¿Dónde vive?
- Gate efectivo de skip: **inline** en `phase_policy_planner_node`.
- Sí existe `backend/negotiation/gating/gate_planner.py` (`gate_phase_policy`) pero **no se invoca** en el nodo planner actual.

### Inputs del gate inline
- `planner_request = progress_state.policy_state.planner_request`
- `advance_step = progress_state.advance_step`
- `judgement_skip_planner = policy_plan_judgement.skip_planner`
- `previous_plan = progress_state.active_plan`

### Orden exacto de decisión
1. `skip_allowed = advance_step or judgement_skip_planner`.
2. Solo evalúa skip si `planner_request == "continue_policy" AND previous_plan AND skip_allowed`.
3. Ruta A (`advance_step=True`): intenta `_advance_step(previous_plan)`.
   - si avanza: `planner_skipped=True`, reason=`advance_step_without_planner`.
   - si no avanza (out of range): fuerza `planner_request="replan_policy"`, marca `advance_step_out_of_range=True`, llama planner.
4. Ruta B (`advance_step=False`, `judgement_skip_planner=True`): clamp step y `planner_skipped=True`, reason=`judge_skip_planner`.
5. Fuera de esas condiciones => Ruta C: **no skip**, llama planner LLM.

### Razones de skip (strings exactos)
- `advance_step_without_planner`
- `judge_skip_planner`
- (vacío cuando no skip)

### Reporte en LiveTrace/telemetría
- `planner_meta.planner_skipped`, `planner_meta.planner_skip_reason`, `planner_meta.judgement_skip_planner`, `planner_meta.advance_step`.
- `gates.planner_skipped` y `gates.skip_reasons.planner` vienen de `state.gate_meta` construido al final del planner node.
- `timing.nodes.phase_policy_planner.skipped` se deriva en `_instrumented_node` leyendo `gate_meta["phase_skipped"]` (bug de coherencia potencial, porque planner escribe `planner_skipped`, no `phase_skipped`).

### Rutas solicitadas
- **A)** Skip por `advance_step=True`: sí implementado (`advance_step_without_planner`) si además `planner_request==continue_policy` y hay `active_plan`.
- **B)** Skip por `judgement_skip_planner=True`: sí implementado (`judge_skip_planner`) bajo misma condición `continue_policy + active_plan`.
- **C)** No skip: llama planner LLM (`deps.plan_phase_policy` + `record_llm_call(name="planner_llm")`).
- **D)** Fallback: planner falla -> fallback en `plan_phase_policy` o fallback externo en `planner_node`.

## 4) PROMPTS DEL PLANNER (planner_llm)

### Confirmación de llamada LLM
Sí, planner llama LLM vía `get_planner_llm().with_structured_output(PhasePolicyDecisionModel).invoke(messages)`.

### SYSTEM prompt (verbatim)
```
Eres un planificador de fase y policy en una negociación.
Devuelve SOLO JSON válido que cumpla el schema solicitado.

Reglas:
- phase debe ser uno de: climate, interests, options, adjust, formalize (temporalmente también se acepta legacy: opening, discovery, bargaining, closing, recovery)
- reasons: etiquetas normalizadas (world:<flag> | belief:<flag> | intent:<flag> | history:<flag>)
- signals: señales observables y cortas.
- policy_id debe estar en allowed_policy_ids.
- No usar hipótesis crudas como hechos; usa solo belief cues gobernantes.
- recovery_mode debe ser true o false. Si hay tensión/loop, puedes activar recovery_mode sin cambiar phase base.
- Después de elegir phase, SOLO puedes elegir una policy cuyas phases incluyan esa phase.
- micro_goal breve y accionable.
- NO texto fuera del JSON, NO markdown.
```

### USER prompt (template)
```
[WorldState]
{world_state}

[World diff]
{world_diff}

[BeliefState]
{belief_state}

[Belief cues governantes]
{belief_cues}

[PolicyState]
{policy_state}

[PolicyPlan summary]
{policy_plan_summary}

[PhaseState prev]
{phase_state}

[Allowed policy ids]
{allowed_policy_ids}

[Policy catalog]
{policy_catalog}

[Policy catalog with phases]
{policy_catalog_with_phases}

[Objective]
{objective}

[Constraints]
{constraints}

[Recent context]
{recent_context}

Devuelve SOLO JSON con phase + recovery_mode + policy.
```

### Variables interpoladas
`world_state`, `world_diff`, `belief_state`, `belief_cues` (gobernados), `policy_state`, `policy_plan_summary`, `phase_state`, `allowed_policy_ids`, `policy_catalog`, `policy_catalog_with_phases`, `objective`, `constraints`, `recent_context`.

### Schema esperado
Se fuerza structured output con `PhasePolicyDecisionModel` (incluye campos usados por código: `phase`, `confidence`, `recovery_mode`, `reasons`, `signals`, `alternatives`, `policy_id`, `reason`, `micro_goal`, `risk_posture`, `why_short`, `inputs_used`).

### Parseo/validación
- parseo por `.with_structured_output(...).invoke(...)` y `result.model_dump()`.
- normalización extra: `_normalize_reasons`, `_normalize_signals`, `normalize_policy_decision`.
- enforce allowlist: si policy no permitida, reemplaza por `allowed_policy_ids[0]`.

### Tokens/latencia/retries en trace
- `planner_node` registra `record_llm_call(name="planner_llm", node="phase_policy_planner", retry_count=1 si fallback_used)`.
- `trace_runtime.record_llm_call[_ms]` agrega `latency_ms`, `ok`, `retry_count`, `error_stage`, `error` en `timing.llm_calls`.

## 5) MODELO, RETRIES, TIMEOUTS, COSTE

- Modelo planner por defecto: `gpt-4.1-nano`.
- Planner config default: `temperature=0.0`, `timeout_s=18`, `max_tokens=320`, `retries=1`, `structured_output=True`, `response_format=json_schema`.
- `get_planner_llm()` construye `ChatOpenAI(**build_chat_openai_kwargs(cfg.planner))` con `max_retries=component.retries`.
- `llm_calls` usa `name="planner_llm"`, `node="phase_policy_planner"`, latencia en ms.
- Diferencia:
  - `planner_fallback_used=True`: se usó fallback seguro tras excepción.
  - `planner_failed=True`: marca fallo del planner (normalmente acompañado de fallback).

## 6) SCHEMA DE ENTRADA/SALIDA DEL PLANNER

### `policy_decision` (campos)
- `policy_id: str`
- `reason: str`
- `micro_goal: str`
- `risk_posture: low|mid|high`
- `capabilities: set|None`
- `why_short: str`
- `inputs_used: list[str]`

### Ejemplo mínimo válido
```json
{
  "policy_id": "safe_neutral",
  "reason": "Mantener seguridad conversacional",
  "micro_goal": "Pedir una aclaración verificable",
  "risk_posture": "low",
  "why_short": "Falta evidencia para avanzar",
  "inputs_used": []
}
```

### Ejemplo completo (con fallback-style)
```json
{
  "policy_id": "safe_neutral",
  "reason": "Fallback seguro por error de planner.",
  "micro_goal": "Mantener conversación abierta con una pregunta breve.",
  "risk_posture": "low",
  "capabilities": null,
  "why_short": "",
  "inputs_used": []
}
```

### Campos opcionales/legacy
- `capabilities` existe en `PolicyDecision` pero planner actual no lo rellena.
- `phase` puede llegar legacy y migrarse en `postprocess_phase_candidate`.

### Normalización
- `normalize_policy_decision` aplica truncados y enforce de allowlist.
- si policy no permitida: issue `policy_id_not_allowed` y sustitución.

## 7) ALLOWED_POLICY_IDS (origen y efecto)

`allowed_policy_ids_with_reasons(...)` evalúa por policy:
1. fase efectiva (`phase` en catálogo de policy)
2. required inputs desde world
3. hard constraints (actualmente `_violates_hard_constraints` siempre `False`)
4. required beliefs (solo si env `POLICY_REQUIRED_BELIEFS_ENABLED=1`)
5. filtro recovery_mode (solo policies seguras + no aggressive)
6. fallback final a `safe_neutral` si vacío.

Se guarda en `planner_meta.allowed_policy_ids` y `state.allowed_policy_ids`; LiveTrace lo expone como `allowed_policy_ids`.

### Tabla
- Fuente: `phase_effective` -> Regla: match de phase catalog -> Resultado: reduce repertorio al dominio de fase -> Riesgo: si fase quedó “climate” por hysteresis, se excluyen políticas de avance.
- Fuente: `world_state` -> Regla: required inputs -> Resultado: bloquea policies sin inputs -> Riesgo: extractor conservador deja vacíos buckets y recorta de más.
- Fuente: `belief_state` (opt-in) -> Regla: required beliefs -> Resultado: filtros extra -> Riesgo: gating dependiente de env, comportamiento no uniforme entre entornos.
- Fuente: `recovery_mode` -> Regla: solo safe/recovery -> Resultado: subconjunto defensivo -> Riesgo: sobre-conservadurismo en loops.

## 8) INTEGRACIÓN CON policy_progress Y JUDGE

### Mapeo `plan_status -> planner_request`
En `update_policy_state`:
- `continue_same_step` -> `planner_request="replan_policy"` (**force_planner**)
- `advance_step` -> `planner_request="continue_policy"` y `progress_state.advance_step=True`
- `completed` -> `planner_request="replan_policy"`, `status="succeeded"`
- `interrupted_replan`/otros -> `planner_request="replan_policy"`

Por tanto, en trazas donde `plan_status=continue_same_step`, ver `planner_request=replan_policy` **es consistente con el código actual** (no invertido).

### Entrada de `judgement.skip_planner`
Se lee en planner node como `judgement_skip_planner`, se guarda en `planner_meta.judgement_skip_planner`, pero **no produce skip salvo que también se cumplan `planner_request==continue_policy` y `active_plan`**.

### Invariantes “legales” (hoy)
- Skip solo posible en rama `continue_policy + active_plan + (advance_step o judgement_skip_planner)`.
- Con `plan_status=continue_same_step`, el sistema fuerza `replan_policy`, por diseño casi nunca skippea planner.

## 9) TELEMETRÍA / LIVETRACE PARA PLANNER

Campos observables:
- `planner_meta`: `planner_failed`, `planner_error`, `planner_fallback_used`, `planner_skipped`, `planner_skip_reason`, `planner_request`, `advance_step`, `judgement_skip_planner`, `allowed_policy_ids`, `planner_llm_called`, `planner_latency_ms`, `planner_error_stage`, `policy_normalization_changed`, `issues`.
- `planner_debug`: bloques `inputs`, `gate_decision`, `plan_handling`, `policy_selection`, `llm_call`, `executor_instruction_contract`.
- `gates`: desde `gate_meta` (`planner_skipped`, `skip_reasons.planner`).
- `timing.nodes.phase_policy_planner`: `entered/skipped/llm_ms/total_ms` desde runtime.
- `timing.llm_calls`: item `planner_llm`.

Consistencia a vigilar:
- `_instrumented_node` usa `skip_key = "phase_skipped"` para `phase_policy_planner`; planner node escribe `planner_skipped`, no `phase_skipped`.
- Esto puede dejar `timing.nodes.phase_policy_planner.skipped` incoherente con `planner_meta.planner_skipped`/`gates.planner_skipped`.

## 10) PROBLEMAS OBSERVADOS + HIPÓTESIS (con LiveTrace)

### Observación A: `plan_status=continue_same_step` + `planner_request=replan_policy`
- Hipótesis confirmada por código: mapeo explícito en `update_policy_state` fuerza replan para `continue_same_step`.
- No parece bug de rename; es diseño actual (agresivo en replanning).

### Observación B: planner no se salta casi nunca
- Causa probable 1: skip solo permitido si `planner_request=continue_policy`.
- Causa probable 2: `continue_same_step` nunca produce `continue_policy`, sino `replan_policy`.
- Causa probable 3: aunque judge tenga `skip_planner=True`, no aplica en rama `replan_policy`.

### Observación C: latencia planner ~9s > judge ~2-3s
- Planner prompt incluye payload grande (`world_state`, `world_diff`, `belief_state`, catálogos completos policies+phases, recent_context), elevando coste de inferencia.
- Judge usa payload más compacto dedicado.

### Observación D: belief_signals conservadores (`recommended_move=hold`, `conflict_risk=0`)
- `plan_phase_policy` pasa `belief_cues` gobernados, pero sin `behavior_guidance` efectivo (vacío), lo que reduce señal táctica y puede sesgar al planner a opciones seguras repetidas.

### Reglas automáticas detectables (flags)
- `if plan_status == continue_same_step and planner_request != replan_policy -> flag_map_drift`
- `if judgement_skip_planner and planner_llm_called -> flag_skip_gate_ignored`
- `if advance_step and not planner_skipped -> flag_advance_without_skip`
- `if planner_skipped and planner_llm_called -> flag_skip_llm_inconsistency`
- `if planner_meta.planner_skipped != gates.planner_skipped -> flag_trace_gate_mismatch`
- `if planner_meta.planner_skipped and timing.nodes.phase_policy_planner.skipped is False -> flag_timing_skip_mismatch`

## 11) PROPUESTAS DE PULIDO (P0/P1/P2)

### P0 (alto impacto, bajo riesgo)
1. **Invariante de coherencia skip/timing/gates**
   - Tocar: `backend/negotiation/negotiation_graph.py` (`_instrumented_node`) y/o `planner_node`.
   - Patch mínimo: para `phase_policy_planner`, leer `planner_skipped` explícitamente en vez de `phase_skipped`.
   - Riesgo: bajo (solo telemetría skipped).
   - Test: caso con skip real y assert de coherencia `planner_meta/gates/timing`.

2. **Flag explícito de decisión de gate planner**
   - Tocar: `planner_node`.
   - Añadir `planner_meta.gate_path` y `planner_meta.gate_reason_codes` replicando `planner_debug.gate_decision`.
   - Riesgo: bajo.
   - Test: asserts en rutas A/B/C.

3. **Regla segura para skip por judgement en continue_same_step (opcional con feature flag)**
   - Tocar: `policy_progress.update_policy_state` y/o `planner_node`.
   - Patch mínimo: cuando `plan_status==continue_same_step` y `judgement.skip_planner=True` y `active_plan` válido -> permitir `continue_policy`.
   - Riesgo: medio-bajo; mitigable con env flag.
   - Métrica: caída de `planner_llm_called` y latencia sin aumentar `continue_loop`.

### P1 (medio)
1. **Compactar payload planner**
   - Tocar: `phase_policy_planner.plan_phase_policy`.
   - Reemplazar dumps completos por resumen (`planner_context_digest`) de buckets relevantes/top-k.
   - Riesgo: medio (puede perder contexto).
   - Test: snapshot de prompt + regresión de selección policy en fixtures.

2. **Cache/reuse parcial cuando no hay cambios materiales**
   - Tocar: `planner_node` + usar `gating/fingerprints.py` (`stable_allowed_ids_hash`, etc.).
   - Riesgo: medio.
   - Métrica: `planner_latency_ms` p50/p95 y ratio de skip.

### P2 (refactors)
1. **Tipado fuerte de `planner_request` y gate result**
   - Tocar: `schemas.py`, `policy_progress.py`, `planner_node.py`.
   - Riesgo: medio por propagación.
   - Test: mypy/pytest de invariantes.

2. **Structured output estricto + contrato versionado**
   - Tocar: `PhasePolicyDecisionModel`, `phase_policy_planner`.
   - Riesgo: medio.
   - Test: contract tests con casos corruptos.

3. **Snapshot tests de prompts planner**
   - Tocar: `backend/tests/test_phase_policy_prompt_format.py` + snapshots.
   - Riesgo: bajo.

## 12) CHECKLIST FINAL (pulido operativo)

1. Corregir coherencia `timing.nodes.phase_policy_planner.skipped` vs `planner_meta.planner_skipped`.
2. Añadir flags de inconsistencia en LiveTrace para map/skip/timing.
3. Decidir semántica oficial de `continue_same_step` (¿forzar replan siempre o permitir skip guiado?).
4. Si se mantiene forzado, documentarlo explícitamente en comentarios y runbooks.
5. Si se cambia, hacerlo bajo feature flag (`PLANNER_SKIP_ON_CONTINUE_SAME_STEP=1`).
6. Añadir test de `judgement.skip_planner=True` + `continue_same_step` para comportamiento esperado.
7. Añadir test de coherencia triple (`planner_meta`, `gates`, `timing.nodes`).
8. Reducir payload del planner (resúmenes en vez de estados completos).
9. Incluir `model` real/tokens en `llm_calls` cuando el provider lo exponga.
10. Añadir dashboard p50/p95 de `planner_latency_ms` + ratio de fallback.
11. Revisar `repair_policy_by_phase` (importado pero no usado en planner node actual) y limpiar o reintegrar.
12. Evaluar conectar `gating/gate_planner.py` o eliminarlo para evitar deuda/confusión.

## Comandos usados para verificar “la verdad” en repo

```bash
rg --files -g 'AGENTS.md'
rg -n "phase_policy_planner|planner_meta|policy_progress|policy_plan_judgement|planner_request|skip_planner|allowed_policy_ids|get_planner_llm|planner_llm|advance_step|plan_status" backend
rg -n "gate_phase_policy\(|stable_allowed_ids_hash|loop_flags_changed\(" backend/negotiation
sed -n '1,260p' backend/negotiation/nodes/planner_node.py
sed -n '1,280p' backend/negotiation/phase_policy_planner.py
sed -n '180,340p' backend/prompts.py
sed -n '1,280p' backend/negotiation/policy_progress.py
sed -n '1,260p' backend/negotiation/nodes/world_node.py
sed -n '1,320p' backend/negotiation/policy_planner.py
sed -n '1,320p' backend/negotiation/config/models.py
sed -n '1,280p' backend/negotiation/telemetry/trace_runtime.py
sed -n '1,340p' backend/negotiation/telemetry/live_trace.py
pytest -q backend/tests/test_policy_progress_and_planner_invariants.py backend/tests/test_phase_policy_prompt_format.py backend/tests/test_live_trace_runtime_wiring.py
```
