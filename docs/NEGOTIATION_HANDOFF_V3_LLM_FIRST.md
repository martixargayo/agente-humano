# Handoff Pack — Sistema de Negociación v3 (LLM-first)

> Documento técnico integral para entender, operar y depurar el pipeline `/negociar` sin contexto previo.

## Índice

1. [TL;DR](#1-tldr)
2. [Arquitectura general](#2-arquitectura-general)
3. [Contratos de estado v3 (schemas)](#3-contratos-de-estado-v3-schemas)
4. [World extraction (Extractor v4) end-to-end](#4-world-extraction-extractor-v4-end-to-end)
5. [Belief updater end-to-end](#5-belief-updater-end-to-end)
6. [Policy progress + Progress updater](#6-policy-progress--progress-updater)
7. [Phase + Policy planner](#7-phase--policy-planner)
8. [Executor (render de respuesta)](#8-executor-render-de-respuesta)
9. [Gates y semántica](#9-gates-y-semantica)
10. [LiveTrace (SSE) y telemetría](#10-livetrace-sse-y-telemetria)
11. [Checklist de depuración rápida](#11-checklist-de-depuracion-rapida)
12. [Archivos source of truth](#12-archivos-source-of-truth)
13. [Estado actual + próximos pasos](#13-estado-actual--proximos-pasos)

---

## 1) TL;DR

### Qué hace `/negociar`

`run_negotiation_agent(...)` en `backend/negotiation/negotiation_graph.py` levanta un turno completo de negociación con LangGraph:

- Ingesta de mensaje usuario + contexto de sesión.
- Actualización de `world_state` (extracción estructurada LLM-first).
- Derivación de `belief_state` y señales para planificación.
- Evaluación de progreso de plan (`policy_plan_judgement` via `world_judge_llm`).
- Planificación de fase/policy (o skip por continuidad de plan).
- Render de respuesta final con executor + validación/reparación.
- Persistencia de estados + trazas (LiveTrace + trace_runtime).

### Qué significa “LLM-first v3”

- **World**: la fuente principal de extracción es el extractor LLM `world_extractor_v4` (`extract_world_patch_llm_v4`), no reglas regex legacy.
- **Planner**: fase/policy se decide por LLM estructurado (`plan_phase_policy`) con lista de `allowed_policy_ids` calculada en backend.
- **Executor**: respuesta textual se genera por LLM (`render_executor_output`) con contratos de estilo/seguridad.
- **Telemetría vNext**: se conserva el payload clásico de trace, pero `build_trace_event` ya emite esquema `trace_schema_version: vNext-1` y agrega runtime por nodo/llm.

### Estable vs en evolución

**Estable hoy**
- Pipeline de nodos (orden fijo).
- Contratos base `WorldState`, `BeliefState`, `ProgressState`, `PolicyDecision`.
- Confidence defaulting + dedupe por `raw_text` en world buckets.
- Semántica de gates expuesta en `gate_choices` (enabled/decision/reason).

**En evolución**
- Calidad táctica real del planner/executor (negociación “más dura” y menos fallback a safe/rapport).
- Enriquecimiento de `planner_debug_v2` como rastro de decisión más explicable.
- LiveTrace vNext todavía coexistiendo con campos “legacy-friendly”.

---

## 2) Arquitectura general

## Diagrama textual del turno

```text
START
  → world_updater
  → belief_updater
  → policy_progress
  → phase_policy_planner
  → progress_updater
  → executor
END
```

Wiring literal en `backend/negotiation/negotiation_graph.py` (`workflow.add_node(...)`, `workflow.add_edge(...)`).

## Qué entra/sale en cada nodo

### 2.1 `world_updater_node(state)`
**Entrada principal**
- `user_message`, `turn_count`, `world_state` previo, `progress_state.gate_state`, `recent_history_text`.

**Salida principal**
- `world_state` actualizado.
- `world_diff`.
- `extractor_meta` (incluye métricas de confidence + gate info + world_judge_meta).
- `policy_plan_judgement` (de `world_judge_llm`).
- actualización de `progress_state.gate_state`.

### 2.2 `belief_updater_node(state)`
**Entrada**
- `prev_belief_state`, `world_state`, `world_diff`, `gate_state`.

**Salida**
- `belief_state` actualizado o reutilizado (si gate skip).
- `belief_update_meta` + `belief_debug`.

### 2.3 `policy_progress_node(state)`
**Entrada**
- `policy_plan_judgement` + `progress_state.policy_state`.

**Salida**
- `policy_state` mutado (`planner_request`: continue/replan).
- `policy_hint`, `policy_meta`.
- contadores de `judgement_missing_streak` y `last_judgement_status`.

### 2.4 `phase_policy_planner_node(state)`
**Entrada**
- `world_state`, `belief_state`, `progress_state`, `policy_state`, `allowed_policy_ids` derivables.

**Salida**
- `phase_candidate`, `phase_effective`.
- `policy_decision`.
- `planner_meta`, `planner_debug`, `planner_debug_v2`.
- `executor_instruction` derivada del `active_plan`.
- `gate_meta` consolidado (world/belief/planner skipped + reasons).

### 2.5 `progress_updater_node(state)`
**Entrada**
- `policy_decision`, `prev/new world_state`, `prev/new belief_state`, `progress_state` previo.

**Salida**
- `progress_state` consolidado (counters, loop_flags, last outcomes, etc.).
- `progress_debug`.

### 2.6 `executor_node(state)`
**Entrada**
- `executed_policy` / `policy_decision`, `executor_instruction`, render profiles, constraints, memory.

**Salida**
- `executor_output`, `assistant_message`, `response` (`final_reply`).
- `executor_validator_meta`, `executor_debug_v2`.

## Source of truth del estado

- **World factual/observacional**: `state.world_state`.
- **Belief interpretativo/planner cues**: `state.belief_state`.
- **Control de progreso y bucles**: `state.progress_state` (incluye `policy_state`, `phase_state`, `gate_state`).
- **Decisión de acción del turno**: `state.policy_decision` + `state.executor_instruction`.
- **Diagnóstico operativo**: `state.planner_meta`, `state.belief_update_meta`, `state.extractor_meta`, `state.trace_runtime`.

---

## 3) Contratos de estado v3 (schemas)

> Definiciones base: `backend/negotiation/schemas.py` + normalizadores en `backend/negotiation/validation.py`.

### 3.1 `WorldState`

Estructura canónica:

```json
{
  "schema_version": "v3",
  "world_buckets": {
    "offers": [],
    "concessions": [],
    "constraints": [],
    "interests": [],
    "claims": [],
    "requests": [],
    "context": []
  },
  "world_state_meta": {
    "last_update_source": "llm",
    "evidence_confidence_min": 0.6,
    "updated_fields": [],
    "turn_idx": 0,
    "unknown_claims": [],
    "error": "",
    "extractor_failed": false,
    "updated_buckets": []
  }
}
```

Ejemplo realista con items:

```json
{
  "schema_version": "v3",
  "world_buckets": {
    "offers": [
      {
        "text": "Propone cerrar hoy si se mantiene el precio publicado.",
        "raw_text": "te lo cierro hoy si me respetas el precio",
        "confidence": 0.84,
        "confidence_defaulted": false,
        "confidence_source": "emitted_by_llm",
        "source_turn": 18
      }
    ],
    "concessions": [],
    "constraints": [
      {
        "text": "No puede pagar más de 12.000 este mes.",
        "raw_text": "más de 12 mil este mes no puedo",
        "confidence": 0.79,
        "confidence_defaulted": false,
        "confidence_source": "emitted_by_llm",
        "source_turn": 18
      }
    ],
    "interests": [],
    "claims": [],
    "requests": [
      {
        "text": "Pide ver mantenimiento documentado.",
        "raw_text": "si tienes facturas del mantenimiento pásamelas",
        "confidence": 0.67,
        "confidence_defaulted": false,
        "confidence_source": "emitted_by_llm",
        "source_turn": 18
      }
    ],
    "context": []
  },
  "world_state_meta": {
    "last_update_source": "llm",
    "evidence_confidence_min": 0.6,
    "updated_fields": ["world_buckets.offers", "world_buckets.constraints", "world_buckets.requests"],
    "turn_idx": 18,
    "unknown_claims": [],
    "error": "",
    "extractor_failed": false,
    "updated_buckets": ["offers", "constraints", "requests"]
  }
}
```

### 3.2 `BeliefState`

Estructura canónica:

```json
{
  "schema_version": "v3",
  "belief_buckets": {
    "hypotheses": [],
    "strategy_notes": [],
    "risk_flags": [],
    "watch_items": []
  },
  "planner_signals": {
    "interaction_health": "stable",
    "conflict_risk": 0.0,
    "recommended_move": "hold",
    "recovery_mode": false,
    "clarity_vague": false
  }
}
```

Ejemplo realista:

```json
{
  "schema_version": "v3",
  "belief_buckets": {
    "hypotheses": [
      {"text": "La otra parte mantiene: te lo cierro hoy si me respetas el precio", "confidence": 0.84, "status": "active"}
    ],
    "strategy_notes": [
      {"text": "Responder a petición: Pide ver mantenimiento documentado.", "confidence": 0.55, "status": "active"}
    ],
    "risk_flags": [
      {"text": "No puede pagar más de 12.000 este mes.", "confidence": 0.79, "status": "active"}
    ],
    "watch_items": []
  },
  "planner_signals": {
    "interaction_health": "tense",
    "conflict_risk": 0.6,
    "recommended_move": "tradeoff",
    "recovery_mode": true,
    "clarity_vague": false
  }
}
```

### 3.3 `policy_plan_judgement`

Sale de `world_judge_llm` (`world_node.py`):

```json
{
  "schema_version": "v1",
  "turn_idx": 18,
  "plan_presence": "active",
  "plan_id": "plan_t17",
  "evaluated_step_idx": 0,
  "plan_status": "continue_same_step",
  "why": "El usuario aún no confirma evidencia requerida.",
  "evidence": [{"quote": "te lo cierro hoy...", "source": "user_message", "span": [0, 28]}],
  "confidence": 0.71,
  "missing_signals": ["confirmacion_precio_final"],
  "safety_flags": [],
  "degraded": false,
  "degrade_reason": ""
}
```

### 3.4 `policy_decision`

Contrato de `PolicyDecision`:

```json
{
  "policy_id": "tradeoff_offer",
  "reason": "Hay restricción explícita de presupuesto y señal de cierre rápido.",
  "micro_goal": "Presentar intercambio simple: precio vs rapidez/certidumbre.",
  "risk_posture": "mid",
  "capabilities": null,
  "why_short": "constraint+urgency",
  "inputs_used": ["world_buckets.constraints", "world_buckets.offers", "planner_signals.conflict_risk"]
}
```

### 3.5 `phase_candidate` y `phase_effective`

`phase_candidate` (salida directa planner):

```json
{
  "phase": "options",
  "confidence": 0.74,
  "recovery_mode": false,
  "reasons": ["world:offer_signal", "belief:tradeoff_move"],
  "signals": [{"source": "world", "key": "offers", "value": "conditional_close"}],
  "alternatives": [{"policy_id": "tradeoff_offer", "reason": "phase_fit_high"}]
}
```

`phase_effective` (tras post-proceso + hysteresis):

```json
{
  "phase": "options",
  "phase_proposed": "options",
  "phase_effective": "options",
  "recovery_mode": false,
  "recovery_stable_turns": 1,
  "confidence": 0.74,
  "reasons": ["world:offer_signal", "belief:tradeoff_move"],
  "last_updated_turn": 18
}
```

### 3.6 `gates`

Estructura de `state.gate_meta` que viaja a trace:

```json
{
  "world_skipped": false,
  "belief_skipped": true,
  "planner_skipped": true,
  "skip_reasons": {
    "world": "",
    "belief": "no_world_delta",
    "planner": "continue_policy"
  }
}
```

### 3.7 User-facing vs interno

**User-facing (LiveTrace principal)**
- `final_reply`, `input_message`, `policy`, `phase`.
- `world_diff`, `belief_diff`, `policy_decision`, `policy_plan_judgement`.
- `gate_choices`, `timing.nodes`, `timing.llm_calls`.
- `extractor_confidence_summary`, `top_evidence_v2`.

**Interno (útil para debug profundo)**
- `planner_debug`, `planner_debug_v2`, `executor_debug_v2`.
- `trace_runtime` completo.
- `belief_update_meta`, `extractor_meta` expandido, `phase_meta`.

---

## 4) World extraction (Extractor v4) end-to-end

Archivos clave:
- `backend/negotiation/extractors/world_extractor_v4.py`
- `backend/negotiation/world_state_updater.py`
- `backend/negotiation/validation.py`

## 4.1 Lifecycle exacto

1. `world_updater_node` llama `update_world_state(...)`.
2. `update_world_state` invoca `extract_world_patch_llm_v4(...)`.
3. `extract_world_patch_llm_v4`:
   - arma prompts (`WORLD_EXTRACTOR_V4_SYSTEM_PROMPT` + `WORLD_EXTRACTOR_V4_USER_PROMPT`).
   - ejecuta LLM (`deps.llm.invoke(...)`/`deps.execute(...)`).
   - parsea con `_safe_json_load`.
   - normaliza cada item con `_normalize_item`.
4. `update_world_state` hace merge con `merge_world_buckets_append_mostly(...)`.
5. aplica `normalize_world_buckets(...)`.
6. actualiza `world_state_meta` (`updated_fields`, `updated_buckets`, `extractor_failed`, `turn_idx`, etc.).
7. devuelve `world_state + meta` a `world_updater_node`.

## 4.2 Snippet prompt extractor (relevante)

```python
# world_extractor_v4.py
RULES:
- Output ONLY this JSON schema:
  {"schema_version":"world_extractor_v4","world_buckets_patch":{...},"meta":{...}}
- raw_text is mandatory for every emitted item.
- confidence is mandatory and must be numeric in [0,1].
- Use confidence >= 0.60 for emitted items...
- Never emit confidence=0 unless the quote explicitly states total uncertainty.
```

## 4.3 Semántica de `confidence` (decisión actual)

### Qué representa
Confianza epistemológica del extractor sobre **la validez de ese item** para planificación, no “certeza ontológica absoluta”.

### Cuándo se defaulta
En `_normalize_item` (extractor) y `_normalize_bucket_item`/`normalize_world_buckets` (updater/validation):
- faltante (`None`) → default 0.6.
- inválido (no float parseable) → default 0.6.
- `<= 0.0` → default 0.6.

### Flags
- `confidence_defaulted: true|false`
- `confidence_source`:
  - `emitted_by_llm` (vino válido del modelo)
  - `defaulted_by_parser` (normalización en extractor)
  - `defaulted_by_normalizer` (normalización merge/validation)

### Reflejo en LiveTrace
- `extractor_confidence_summary` dentro de trace item/event:
  - `emitted_count`, `missing_count`, `zeros_count`, `min/max/avg`, `per_bucket`.
- `top_evidence_v2` muestra top claims por confianza para lectura rápida.

## 4.4 Dedupe por `raw_text` y winner

`merge_world_buckets_append_mostly` usa clave `_bucket_dedupe_key(item)`:
1. prioriza `raw_text` normalizado (lower + sin acentos + colapso espacios).
2. si no hay `raw_text`, cae a `text`.

Si hay colisión de clave:
- conserva el item con mayor `confidence`.

**Por qué**: evita duplicados semánticos por paraphrase y mantiene la mejor evidencia de una cita específica del usuario.

---

## 5) Belief updater end-to-end

Archivos:
- `backend/negotiation/belief_state_updater.py`
- `backend/negotiation/nodes/belief_node.py`

## 5.1 Flujo (LLM-first + gate por delta real de world)

1. `belief_updater_node` evalúa si hubo cambio significativo en `world_state.world_buckets`.
   - Preferencia 1: revisa `world_diff.domain.world_buckets` o `world_diff.world_buckets`.
   - Preferencia 2: compara `prev_world_state.world_buckets != world_state.world_buckets`.
   - Cambios solo de `world_state_meta` no abren gate.
2. Si NO hay delta real:
   - `belief_update_skipped = true`
   - `skip_reason = "no_world_delta"`
   - no se llama LLM y se reutiliza `belief_state` previo sin mutación.
3. Si SÍ hay delta real:
   - llama `extract_belief_state_llm_v1(...)`.
   - `belief_engine = "llm_belief_extractor_v1"`
   - `belief_llm_used = true`
4. El extractor normaliza salida estricta v3:
   - `schema_version = "v3"`
   - buckets `hypotheses/strategy_notes/risk_flags/watch_items`
   - `planner_signals` (`interaction_health`, `conflict_risk`, `recommended_move`, `recovery_mode`).

## 5.2 Telemetría y LiveTrace

Cuando corre belief LLM:
- `timing.llm_calls[]` incluye `{"name":"belief_llm","node":"belief_updater", ...}`.
- `timing.nodes.belief_updater.llm_ms > 0`.

Cuando se salta belief:
- no aparece `belief_llm` en `timing.llm_calls`.
- gate/meta exponen `belief_update_skipped=true`, `skip_reason="no_world_delta"`.

## 5.3 Reglas de normalización del extractor

- `conflict_risk` clamp a `[0,1]`.
- `status` forzado a `{active, weakening, new}`.
- límites de tamaño en texto y arrays.
- se ignoran keys legacy que no pertenezcan al contrato v3.

---

## 6) Policy progress + Progress updater

Archivos:
- `backend/negotiation/nodes/policy_progress_node.py`
- `backend/negotiation/policy_progress.py`
- `backend/negotiation/nodes/progress_node.py`
- `backend/negotiation/progress_updater.py`

## 6.1 `policy_plan_judgement`: none → active

- Se setea en `world_updater_node` vía `world_judge_llm`.
- `policy_progress_node`:
  - si existe dict válido: `judgement_missing_streak = 0`, actualiza `last_judgement_status`.
  - si falta: incrementa `judgement_missing_streak`, marca `last_judgement_status = "missing"`.

## 6.2 `plan_status` y `planner_request`

`update_policy_state` mapea:
- `continue_same_step` → `planner_request = continue_policy`.
- `advance_step` → `planner_request = continue_policy` + `progress_state.advance_step = true`.
- `completed` → `planner_request = replan_policy`, `policy_state.status = succeeded`.
- otro/ausente → `planner_request = replan_policy` (`interrupted_replan`).

## 6.3 `missing_signals`: normal vs bug

**Normal**
- Lista vacía cuando evidencia suficiente o judge degradado conservador.
- Campos como `confirmacion_precio_final` cuando no hay evidencia dura para avanzar.

**Bug sospechoso**
- `missing_signals` siempre con valores irrelevantes aunque cambie el diálogo.
- `plan_status=advance_step/completed` repetido con `evidence=[]` (debería autocorregirse a `continue_same_step`).

---

## 7) Phase + Policy planner

Archivos:
- `backend/negotiation/nodes/planner_node.py`
- `backend/negotiation/phase_policy_planner.py`
- `backend/negotiation/phase_state_updater.py`
- `backend/negotiation/policy_planner.py`

## 7.1 `phase_candidate` y hysteresis hacia `phase_effective`

1. `plan_phase_policy(...)` devuelve `phase_candidate` (phase + confidence + reasons/signals).
2. `postprocess_phase_candidate(...)`:
   - normaliza phase (incluye mapeo legacy).
   - calcula `recovery_mode` operativo.
   - aplica gate semántico de fase (`_gate_effective_phase`).
   - aplica hysteresis (`_apply_hysteresis`): si cambio de fase no supera umbral (0.62/0.72 según distancia), se mantiene fase previa.

## 7.2 `allowed_policy_ids`

`allowed_policy_ids_with_reasons(...)` filtra por:
- compatibilidad con `phase_effective`.
- `required_inputs` sobre world.
- hard constraints (hoy `_violates_hard_constraints` retorna false).
- opcionalmente required beliefs (flag `POLICY_REQUIRED_BELIEFS_ENABLED`).
- filtro extra en recovery mode (solo safe/recovery-tagged).

## 7.3 Decisión final `policy_decision.policy_id`

Cadena de decisión:
1. LLM planner sugiere `policy_id` estructurado (`PhasePolicyDecisionModel`).
2. `normalize_policy_decision` valida formato + allowlist.
3. si no permitido: se reemplaza por primer allowed.
4. fallback en excepción: `_fallback_policy(...)` / `default_policy_decision`.

## 7.4 `planner_skipped` y `planner_skip_reason=continue_policy`

En `phase_policy_planner_node`:
- si `planner_request == continue_policy` y hay `active_plan`:
  - sin `advance_step`: no llama LLM, reutiliza plan y setea:
    - `planner_skipped = true`
    - `planner_skip_reason = "continue_policy"`
  - con `advance_step=true`: intenta avanzar step sin LLM (`advance_step_without_planner`).

## 7.5 Snippet llamada LLM planner + métricas

```python
# nodes/planner_node.py
started = time.perf_counter()
phase_candidate, policy_decision, planner_call_meta = deps.plan_phase_policy(...)
planner_debug["llm_call"]["planner_llm_called"] = True
planner_debug["llm_call"]["planner_latency_ms"] = int((time.perf_counter()-started)*1000)
record_llm_call(state, name="planner_llm", node="phase_policy_planner", started=started, ...)
```

Y dentro de `plan_phase_policy`:

```python
structured = get_planner_llm().with_structured_output(PhasePolicyDecisionModel)
result = structured.invoke(messages)
meta["planner_llm_called"] = True
meta["planner_latency_ms"] = int((time.perf_counter()-started)*1000)
```

## 7.6 `planner_debug_v2`

Si trace internals está activo (`TRACE_INCLUDE_INTERNALS=1` o `TRACE_LEVEL>=2`), LiveTrace incluye:
- `input_compact`: phase efectiva, allowed ids, planner_request, gate decisions influyentes.
- `output`: selected policy, ranking top alternativas, normalization/fallback.
- `reasoning_trace`: `why_short`, key factors, alternativas rechazadas.

---

## 8) Executor (render de respuesta)

Archivos:
- `backend/negotiation/nodes/executor_node.py`
- `backend/negotiation/executor/render_executor.py`
- prompts en `backend/negotiation/elementos/render/executor_prompts.py`

## 8.1 Uso de `executed_policy` + `micro_goal`

- `executor_node` toma `policy_decision` y lo asigna a `executed_policy` si no existe.
- Construye `strategy_summary` (`build_strategy_summary`) que incluye `policy_id`, `micro_goal`, `why_short`, `phase_effective`, `executor_instruction`.
- Ese summary alimenta el prompt del executor.

## 8.2 Templates/prompts por policy

No hay un template separado por cada policy dentro de executor node; hay prompt unificado (`EXECUTOR_USER_PROMPT`) con campos inyectados (`policy_id`, `micro_goal`, hints, constraints, etc.).

## 8.3 Validadores / post-repair

Pipeline:
1. LLM render (`render_executor_output`).
2. `validate_and_repair(...)` aplica guardas de formato/claims/comportamiento.
3. `_enforce_executor_instruction(...)` aplica reglas de step (`must_avoid`, `max_questions_per_turn`, `safe_mode`).
4. si hubo fallback/repair, reemplaza `response_text` final.

## 8.4 Producción de `final_reply`

`state["assistant_message"]` y `state["response"]` se setean desde `executor_output.response_text`; luego `run_negotiation_agent` persiste ese texto en historial y trace como `assistant_reply`/`final_reply`.

## 8.5 Snippet llamada `executor_llm`

```python
# nodes/executor_node.py
llm_started = time.perf_counter()
executor_output = render_executor_output(...)
record_llm_call(state, name="executor_llm", node="executor", started=llm_started, ok=True, model=None)
```

Y en renderer:

```python
# executor/render_executor.py
messages = [SystemMessage(content=EXECUTOR_SYSTEM_PROMPT), HumanMessage(content=prompt)]
raw = deps.execute(messages)
data = safe_json_load(text)
return normalize_executor_output(data)
```

---

## 9) Gates y semántica

## 9.1 Diferencia semántica

- `gate_enabled`: hoy en `_gate_choices` se reporta `true` fijo (semántica de “gate existe/está cableado”).
- `gate_decision`: `executed` o `skipped` según flag booleano `*_skipped`.
- `gate_reason`: razón humana desde `skip_reasons.<gate>`.

## 9.2 Ejemplo real de `gate_choices` (LiveTrace)

```json
[
  {
    "gate": "world",
    "gate_enabled": true,
    "gate_decision": "executed",
    "gate_reason": "",
    "raw_flag": "world_skipped",
    "raw_value": false
  },
  {
    "gate": "belief",
    "gate_enabled": true,
    "gate_decision": "skipped",
    "gate_reason": "no_world_delta",
    "raw_flag": "belief_skipped",
    "raw_value": true
  },
  {
    "gate": "planner",
    "gate_enabled": true,
    "gate_decision": "skipped",
    "gate_reason": "continue_policy",
    "raw_flag": "planner_skipped",
    "raw_value": true
  }
]
```

## 9.3 Dónde se calculan

- `state.gate_meta` se arma en `nodes/planner_node.py`.
- `gate_choices` se deriva en `telemetry/live_trace.py` (`_gate_choices`).
- Node skip timing se marca desde `_instrumented_node` + `trace_runtime.finish_node_timer(... skipped=...)` en `negotiation_graph.py`.

---

## 10) LiveTrace (SSE) y telemetría

Archivos:
- `backend/negotiation/telemetry/live_trace.py`
- `backend/negotiation/telemetry/trace_runtime.py`
- `backend/negotiation/negotiation_graph.py`

## 10.1 TraceEvent “legacy” vs vNext

No hay dos endpoints separados; `build_trace_event(...)` emite payload híbrido con:
- `trace_schema_version = "vNext-1"` cuando `TRACE_LEVEL >= 1`.
- campos legacy aún presentes (`world_*_keys`, `planner_failed`, `policy`, etc.).
- campos vNext operativos (`gate_choices`, `timing.nodes`, `timing.llm_calls`, `planner_debug_v2`, `executor_debug_v2`).

## 10.2 `build_trace_event`

`live_trace.build_trace_event(...)`:
1. lee `trace_item` guardado en `state.debug_trace`.
2. calcula diffs/keys changed-unchanged.
3. transforma gates (`_gate_choices`).
4. arma timing con `_timing_payload` usando `trace_runtime`.
5. adjunta internals condicionales (`_internal_payload`).
6. retorna evento final serializable para SSE.

## 10.3 Cómo se adjunta `trace_runtime`

- Al inicio de cada turno, `graph_state` inicializa `trace_runtime = init_trace_runtime()`.
- Cada nodo instrumentado llama `start_node_timer/finish_node_timer`.
- Llamadas LLM se registran vía `record_llm_call` o `record_llm_call_ms`.
- Al final, `run_negotiation_agent` copia `new_graph_state["trace_runtime"]` dentro de cada `debug_trace` item.

## 10.4 Campos clave de depuración

- `world_diff`, `belief_diff`.
- `planner_meta` (`planner_failed`, `planner_skipped`, `planner_skip_reason`, `issues`).
- `timing.nodes` por nodo (`total_ms`, `gates_ms`, `normalize_merge_diff_ms`, `llm_ms`, `entered`, `skipped`).
- `timing.llm_calls` (`name`, `node`, `latency_ms`, `ok`, `error_stage`, `retry_count`).

## 10.5 Evento ejemplo resumido

```json
{
  "trace_schema_version": "vNext-1",
  "turn": 18,
  "policy": "tradeoff_offer",
  "phase": "options",
  "gate_choices": [
    {"gate": "world", "gate_decision": "executed", "gate_reason": ""},
    {"gate": "belief", "gate_decision": "executed", "gate_reason": ""},
    {"gate": "planner", "gate_decision": "skipped", "gate_reason": "continue_policy"}
  ],
  "timing": {
    "turn_total_ms": 812,
    "nodes": {
      "world_updater": {"total_ms": 210, "llm_ms": 88, "entered": true, "skipped": false},
      "phase_policy_planner": {"total_ms": 7, "llm_ms": 0, "entered": true, "skipped": true},
      "executor": {"total_ms": 344, "llm_ms": 311, "entered": true, "skipped": false}
    },
    "llm_calls": [
      {"name": "world_judge_llm", "node": "world_updater", "latency_ms": 88, "ok": true},
      {"name": "executor_llm", "node": "executor", "latency_ms": 311, "ok": true}
    ]
  }
}
```

## 10.6 Flags de entorno

- `TRACE_LEVEL` (0..3) en `trace_runtime.trace_level()`:
  - 0: mínimo.
  - >=1: marca `trace_schema_version` vNext.
  - >=2: por defecto habilita internals.
- `TRACE_INCLUDE_INTERNALS`:
  - si unset: depende de `TRACE_LEVEL>=2`.
  - si `1`: fuerza incluir `planner_debug_v2`/`executor_debug_v2`.

---

## 11) Checklist de depuración rápida

## 11.1 Si “duración n/a”

Mirar:
- `trace_item` tenga `t_turn_start`, `t_summary_enqueued`.
- `timing` construido por `_timing_payload` usa esos timestamps.

Causa típica:
- trace_item incompleto o serialización parcial antes de guardar `debug_trace`.

## 11.2 Si `timing.nodes` todo 0

Se rompió wiring de `trace_runtime`:
- no se inicializa `trace_runtime` en `graph_state`.
- no se usa `_instrumented_node` (por eso no corre `start_node_timer/finish_node_timer`).
- algún nodo reemplaza `state` y pierde la rama `trace_runtime`.

## 11.3 Si `llm_calls` vacío pero `planner_llm_called=true`

Buscar falta de `record_llm_call(...)` en path planner:
- `planner_node` ya lo hace en rama replan.
- si hubo excepción fuera de ese bloque, puede quedar meta=true sin record.
- `_timing_payload` agrega un fallback sintético planner_llm si detecta esa inconsistencia.

## 11.4 Si planner cae demasiado en `rapport_build`

Revisar en orden:
1. `allowed_policy_ids` (¿quedó solo safe?).
2. `phase_effective` + `recovery_mode` (si recovery=true filtra agresivas).
3. `planner_signals.conflict_risk` alto permanente.
4. `policy_plan_judgement` en `continue_same_step` infinito + `loop_flags`.
5. `planner_meta.issues` / `planner_fallback_used` (si falla planner, cae al fallback seguro).

---

## 12) Archivos “source of truth”

- **Runtime graph wiring**
  - `backend/negotiation/negotiation_graph.py`
  - Entry: `run_negotiation_agent(...)`, `workflow` LangGraph, `_instrumented_node(...)`.

- **Extractor world**
  - `backend/negotiation/extractors/world_extractor_v4.py`
  - Entry: `extract_world_patch_llm_v4(...)`.

- **World merge/normalize**
  - `backend/negotiation/world_state_updater.py`
  - Entry: `update_world_state(...)`, `merge_world_buckets_append_mostly(...)`.
  - `backend/negotiation/validation.py`
  - Entry: `normalize_world_buckets(...)`, `normalize_world_state(...)`.

- **Belief updater**
  - `backend/negotiation/nodes/belief_node.py`
  - Entry: `belief_updater_node(...)`.
  - `backend/negotiation/belief_state_updater.py`
  - Entry: `update_belief_state(...)`.

- **Planner**
  - `backend/negotiation/nodes/planner_node.py`
  - Entry: `phase_policy_planner_node(...)`.
  - `backend/negotiation/phase_policy_planner.py`
  - Entry: `plan_phase_policy(...)`.
  - `backend/negotiation/phase_state_updater.py`
  - Entry: `postprocess_phase_candidate(...)`.
  - `backend/negotiation/policy_planner.py`
  - Entry: `allowed_policy_ids_with_reasons(...)`.

- **Executor**
  - `backend/negotiation/nodes/executor_node.py`
  - Entry: `executor_node(...)`.
  - `backend/negotiation/executor/render_executor.py`
  - Entry: `render_executor_output(...)`.

- **LiveTrace/trace_runtime**
  - `backend/negotiation/telemetry/live_trace.py`
  - Entry: `build_trace_event(...)`, `list_recent_trace_events(...)`.
  - `backend/negotiation/telemetry/trace_runtime.py`
  - Entry: `init_trace_runtime(...)`, `record_llm_call(...)`, `record_llm_call_ms(...)`.

---

## 13) Estado actual del proyecto + próximos pasos

## 13.1 Issues resueltos (estado actual)

1. **Confidence=0 o missing en world buckets**
   - Resuelto con defaulting robusto a 0.6 en extractor + normalizers.
   - Se trazan `confidence_defaulted` y `confidence_source`.

2. **Semántica de gates poco legible**
   - Resuelto con `gate_choices` normalizado (`gate_enabled`, `gate_decision`, `gate_reason`).

3. **Observabilidad de latencias por nodo/LLM**
   - Resuelto con `trace_runtime.nodes` + `trace_runtime.llm_calls` y consolidación en `timing`.

4. **Planner call invisibles en trace**
   - Mitigado con fallback de `_timing_payload` cuando `planner_llm_called=true` pero falta call explícita.

## 13.2 Issues pendientes

1. **Planner/executor todavía conservadores en negociación real**
   - Necesita mejor ranking táctico por contexto y menor dependencia de fallback seguro.

2. **Contratos híbridos legacy/vNext**
   - Hay deuda en limpiar campos legacy redundantes cuando vNext esté cerrado.

3. **Hard constraints reales**
   - `_violates_hard_constraints(...)` hoy no aplica reglas fuertes (siempre false).

4. **Belief updater aún heurístico**
   - Aunque estable, no usa inferencia rica por LLM en este path (tradeoff entre costo/robustez).

## 13.3 Métricas recomendadas desde ahora

- Latencia p50/p95 por nodo (`timing.nodes.<node>.total_ms`).
- Latencia y tasa de error por llamada LLM (`timing.llm_calls`).
- Distribución de `policy_decision.policy_id` por fase.
- Ratio de `planner_skipped` y desglose de `planner_skip_reason`.
- Ratio `planner_fallback_used` y `planner_failed`.
- Ratio `belief_update_skipped` / `world_skipped` por conversación.
- Tasa de `recovery_mode=true` y duración media en recovery.
- Frecuencia de `continue_loop`/`replan_churn`/`stuck_in_policy` en `loop_flags`.

---

## Apéndice A — Snippets de wiring (resumen corto)

### A.1 Orden de nodos (LangGraph)

```python
workflow.add_edge(START, "world_updater")
workflow.add_edge("world_updater", "belief_updater")
workflow.add_edge("belief_updater", "policy_progress")
workflow.add_edge("policy_progress", "phase_policy_planner")
workflow.add_edge("phase_policy_planner", "progress_updater")
workflow.add_edge("progress_updater", "executor")
workflow.add_edge("executor", END)
```

### A.2 Gate meta consolidado

```python
state["gate_meta"] = {
  "world_skipped": state.get("extractor_meta", {}).get("extractor_skipped", False),
  "belief_skipped": state.get("belief_update_meta", {}).get("belief_update_skipped", False),
  "planner_skipped": planner_skipped,
  "skip_reasons": {
    "world": state.get("extractor_meta", {}).get("skip_reason", ""),
    "belief": state.get("belief_update_meta", {}).get("skip_reason", ""),
    "planner": skip_reason,
  },
}
```

### A.3 Registro de trace runtime en trace item

```python
"trace_runtime": new_graph_state.get("trace_runtime", init_trace_runtime()),
"extractor_confidence_summary": new_graph_state.get("extractor_meta", {}).get("extractor_confidence_summary", {...}),
"top_evidence_v2": top_evidence_v2(new_world_state),
```

---

Fin.
