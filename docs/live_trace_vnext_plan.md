# LiveTrace vNext — Plan de ampliación de trazas internas con control de payload y privacidad

## Objetivo
Diseñar una evolución incremental de LiveTrace SSE para exponer internals de planner y executor + latencias por nodo/LLM, manteniendo compatibilidad, límites de tamaño y scrub de datos sensibles.

---

## 1) Estándar de instrumentación de latencias (obligatorio)

### 1.1 Estructura canónica propuesta (`timing`)
```json
{
  "timing": {
    "turn_total_ms": 0,
    "timeline": {
      "t_turn_start": 0.0,
      "t_before_graph": 0.0,
      "t_after_graph": 0.0,
      "t_reply_saved": 0.0,
      "t_summary_enqueued": 0.0
    },
    "nodes": {
      "world_updater": {
        "total_ms": 0,
        "gates_ms": 0,
        "normalize_merge_diff_ms": 0,
        "llm_ms": 0,
        "entered": true,
        "skipped": false
      },
      "belief_updater": {"total_ms": 0, "gates_ms": 0, "normalize_merge_diff_ms": 0, "llm_ms": 0, "entered": true, "skipped": false},
      "policy_progress": {"total_ms": 0, "gates_ms": 0, "normalize_merge_diff_ms": 0, "llm_ms": 0, "entered": true, "skipped": false},
      "phase_policy_planner": {"total_ms": 0, "gates_ms": 0, "normalize_merge_diff_ms": 0, "llm_ms": 0, "entered": true, "skipped": false},
      "progress_updater": {"total_ms": 0, "gates_ms": 0, "normalize_merge_diff_ms": 0, "llm_ms": 0, "entered": true, "skipped": false},
      "executor": {"total_ms": 0, "gates_ms": 0, "normalize_merge_diff_ms": 0, "llm_ms": 0, "entered": true, "skipped": false}
    },
    "llm_calls": [
      {
        "name": "planner_llm",
        "node": "phase_policy_planner",
        "start_ts": "2026-01-01T10:10:10.123Z",
        "end_ts": "2026-01-01T10:10:10.901Z",
        "latency_ms": 778,
        "model": "gpt-4o-mini",
        "tokens_in": null,
        "tokens_out": null,
        "retry_count": 0,
        "ok": true,
        "error_stage": "",
        "error": "",
        "fallback_model_used": false,
        "fallback_model": ""
      }
    ]
  }
}
```

### 1.2 Estrategia de implementación
- Añadir un `trace_runtime` en el estado del grafo para acumular métricas por nodo sin cambiar lógica de negocio.
- Crear helpers reutilizables:
  - `start_node_timer(node_name)` / `finish_node_timer(...)`
  - `record_node_phase_ms(node_name, phase_name, elapsed_ms)`
  - `record_llm_call(...)`
- Registrar `turn_total_ms` derivado de `t_turn_start` y `t_summary_enqueued`.
- Registrar `llm_calls` en los puntos de invocación ya existentes (planner/world/executor/belief cuando aplique).

### 1.3 Ubicación técnica (archivos/funciones)
- `backend/negotiation/negotiation_graph.py`
  - `run_negotiation_agent` (inicialización `trace_runtime`, consolidación final).
- `backend/negotiation/nodes/world_node.py`
  - `world_updater_node`, `world_judge_llm`.
- `backend/negotiation/nodes/belief_node.py`
  - `belief_updater_node`.
- `backend/negotiation/nodes/policy_progress_node.py`
  - `policy_progress_node`.
- `backend/negotiation/nodes/planner_node.py`
  - `phase_policy_planner_node`.
- `backend/negotiation/nodes/progress_node.py`
  - `progress_updater_node`.
- `backend/negotiation/nodes/executor_node.py`
  - `executor_node`.
- `backend/negotiation/telemetry/live_trace.py`
  - `build_trace_event` (mapeo final a SSE).

---

## 2) Trazas internas planner (muy detallado y seguro)

### 2.1 `planner_debug_v2.input_compact`
Campos (compactados/redactados):
- `phase_effective`
- `world_buckets_topn` (por bucket: top-N por confidence)
- `belief_buckets_topn` (por bucket: top-N)
- `allowed_policy_ids`
- `planner_request` (`continue_policy`, `advance_step`, `replan_reason`)
- `gate_decisions_influential` (solo las decisiones que afectaron path)

### 2.2 `planner_debug_v2.output`
- `selected_policy`
- `policy_ranking_top5`: `[ {policy_id, score, reason_short} ]`
- `signals_used`: `[ {signal, value, weight|null} ]`
- `normalization`: `{pre_policy_id, post_policy_id, changed, issues}`
- `fallback`: `{used, type, reason, evidence}`

### 2.3 `planner_debug_v2.reasoning_trace`
Sin CoT libre; solo estructura:
- `selected_policy`
- `why_short`
- `key_factors` (lista corta)
- `rejected_alternatives` (máx 4) con `reason_short`

---

## 3) Trazas internas executor (muy detallado y seguro)

### 3.1 `executor_debug_v2.policy_context`
- `executed_policy_id`
- `micro_goal`
- `constraints_struct_rendered`
- `safety_checks_applied`

### 3.2 `executor_debug_v2.render_pipeline`
- `prompt_template_id`
- `validators_run`: `[ {name, ok, issues_count} ]`
- `post_repair`: `{applied, before_compact, after_compact, reason}`

### 3.3 `executor_debug_v2.llm`
- `llm_calls_ref` (ids que apuntan a `timing.llm_calls`)
- `retries`
- `model_fallback`

### 3.4 `executor_debug_v2.output_meta`
- `response_chars`
- `response_words`
- `constraints_respected`
- `sanitizer_flags`

---

## 4) Control de tamaño y privacidad (obligatorio)

### 4.1 Trace levels y flags
- `TRACE_LEVEL=0`: mínimo (health + policy + phase + errores críticos + `turn_total_ms`).
- `TRACE_LEVEL=1`: baseline actual (campos actuales + timing de nodo resumido).
- `TRACE_LEVEL=2`: internals estructurados planner/executor + `llm_calls` completos compactados.
- `TRACE_LEVEL=3` (solo dev): permite prompts más completos, siempre con scrubber.
- Flag adicional: `TRACE_INCLUDE_INTERNALS=true|false` (gate maestro de internals).

### 4.2 Sampling
- `TRACE_SAMPLE_RATE` (0.0-1.0):
  - demo/staging: `1.0`
  - producción: `0.01` a `0.05`
- `TRACE_FORCE_ON_ERROR=true`: siempre trazar completo en error/fallback.
- `TRACE_FORCE_ON_FALLBACK=true`: siempre trazar completo si hay fallback.

### 4.3 Redacción y compactación
- `TRACE_MAX_TEXT_CHARS` (default 240)
- `TRACE_MAX_REASON_CHARS` (default 140)
- `TRACE_BUCKET_TOP_N` (default 3)
- `TRACE_MAX_LIST_ITEMS` (default 8)
- `TRACE_INCLUDE_RAW_PROMPTS=false` (solo true con level 3)

### 4.4 Scrubbing de sensibles
- Scrubber central previo a emitir SSE:
  - emails, teléfonos, DNI/NIF-like patterns
  - números largos de tarjeta
  - secuencias de API keys conocidas
- Reemplazo por tags (`[REDACTED_EMAIL]`, etc.).

---

## 5) Plan por PRs (secuencia segura)

## PR-A — Timing por nodo + LLM calls (sin tocar lógica)

### Cambios exactos
- `backend/negotiation/telemetry/trace_runtime.py` (nuevo): helpers de cronometraje.
- `backend/negotiation/negotiation_graph.py`: inicializar y consolidar `trace_runtime`.
- `backend/negotiation/nodes/*.py`: instrumentación start/end por nodo.
- `backend/negotiation/telemetry/live_trace.py`: publicar `timing.nodes` + `timing.llm_calls`.

### Tests
- `backend/tests/test_live_trace_timing_vnext.py`:
  - shape snapshot de `timing.nodes` y `timing.llm_calls`.
  - asserts de latencia no negativa.
- Ajuste `backend/scripts/trace_payload_stats.py` para medir p95 con nuevos campos.

### Guardrails CI
- Nuevo test/step: falla si `p95_bytes > TRACE_PAYLOAD_P95_BUDGET_BYTES`.

## PR-B — Planner internals estructurados

### Cambios exactos
- `backend/negotiation/nodes/planner_node.py`: construir `planner_debug_v2`.
- `backend/negotiation/phase_policy_planner.py`: exponer ranking/señales/fallback compacto.
- `backend/negotiation/telemetry/live_trace.py`: emisión condicionada por trace level.

### Tests
- `backend/tests/test_planner_debug_v2_trace.py`:
  - asserts `input_compact`, `policy_ranking_top5`, `reasoning_trace`.
  - asserts truncado/top-N.

### Guardrails CI
- test de presupuesto de tamaño con `TRACE_LEVEL=2`.
- test de no inclusión de raw prompts cuando `TRACE_LEVEL<3`.

## PR-C — Executor internals estructurados

### Cambios exactos
- `backend/negotiation/nodes/executor_node.py`: `executor_debug_v2`.
- `backend/negotiation/executor/render_executor.py`: metadata de render/validators/post-repair.
- `backend/negotiation/telemetry/live_trace.py`: mapping y gating por flags.

### Tests
- `backend/tests/test_executor_debug_v2_trace.py`:
  - validators run, post-repair before/after compact, compliance flags.

### Guardrails CI
- budget payload p95 + scrubber assertions.

## PR-D — UI LiveTrace mejoras

### Cambios exactos
- Front UI LiveTrace (archivo/s de frontend donde se renderiza evento SSE):
  - filtros: `node_slow`, `latency_sort`, `llm_model`, `fallback_or_error`.
  - card con tablas: `Node timing`, `LLM calls`.
  - secciones colapsables: `Planner internals`, `Executor internals`.

### Tests
- tests de render + filtrado en UI (según stack: unit/integration).
- snapshots de cards expandido/colapsado.

### Guardrails CI
- limite de filas renderizadas + virtualización si hay alto volumen.

---

## 6) Requisitos UI LiveTrace (especificación funcional)

### Filtros
- `slow_node_only` (umbral configurable, p.ej. `>300ms`)
- `sort_by_latency` (`turn_total_ms`, `node.total_ms`, `llm.latency_ms`)
- `llm_model` (multi-select)
- `fallback_used_or_errors` (boolean)

### Card de evento
- Tabla **Node timing**: nodo, total, gates, normalize/merge/diff, llm, skipped.
- Tabla **LLM calls**: name, node, model, latency, retries, tokens, ok/error.
- Acordeón **Planner internals**.
- Acordeón **Executor internals**.

---

## 7) Estrategia de compatibilidad y rollout

- Mantener campos actuales (`timing.timeline`, `planner_debug`) hasta completar migración de UI.
- Añadir `trace_schema_version: "vNext-1"`.
- Rollout:
  1. activar backend con `TRACE_LEVEL=1`
  2. activar UI tolerante a campos opcionales
  3. subir a `TRACE_LEVEL=2` en staging
  4. producción con sampling + force-on-error

---

## 8) Criterios de aceptación

- SSE no roto para consumidores actuales.
- `timing.nodes` completo en los 6 nodos.
- `timing.llm_calls` poblado cuando haya invocación LLM.
- planner/executor internals visibles con `TRACE_LEVEL>=2`.
- p95 de payload dentro de presupuesto CI.
- scrubber sin fugas de PII en fixtures de prueba.

---

## 9) Campos nuevos y límites propuestos (entregable)

| Campo | Tipo | Límite |
|---|---|---|
| `trace_schema_version` | string | fijo `vNext-1` |
| `timing.turn_total_ms` | number | `>=0` |
| `timing.nodes.*.total_ms` | number | `>=0` |
| `timing.nodes.*.gates_ms` | number | `>=0` |
| `timing.nodes.*.normalize_merge_diff_ms` | number | `>=0` |
| `timing.nodes.*.llm_ms` | number | `>=0` |
| `timing.llm_calls` | array | max 12 items |
| `timing.llm_calls[].name` | string | max 48 chars |
| `timing.llm_calls[].model` | string/null | max 80 chars |
| `timing.llm_calls[].error` | string | max 240 chars |
| `planner_debug_v2.output.policy_ranking_top5` | array | max 5 items |
| `planner_debug_v2.reasoning_trace.key_factors` | array | max 6 items |
| `planner_debug_v2.reasoning_trace.rejected_alternatives` | array | max 4 items |
| `executor_debug_v2.render_pipeline.validators_run` | array | max 10 items |
| `*_buckets_topn` | array por bucket | top-N configurable (`TRACE_BUCKET_TOP_N`, default 3) |
| Textos libres (`reason`, `why_short`, etc.) | string | truncado por `TRACE_MAX_TEXT_CHARS`/`TRACE_MAX_REASON_CHARS` |

Variables de control:
- `TRACE_LEVEL` (0/1/2/3)
- `TRACE_INCLUDE_INTERNALS` (bool)
- `TRACE_SAMPLE_RATE` (0.0..1.0)
- `TRACE_FORCE_ON_ERROR` (bool)
- `TRACE_FORCE_ON_FALLBACK` (bool)
- `TRACE_BUCKET_TOP_N` (int)
- `TRACE_MAX_TEXT_CHARS` (int)
- `TRACE_MAX_REASON_CHARS` (int)
- `TRACE_MAX_LIST_ITEMS` (int)
- `TRACE_INCLUDE_RAW_PROMPTS` (bool, solo nivel 3)
