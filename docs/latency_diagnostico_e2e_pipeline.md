# Diagnóstico técnico de latencia E2E del pipeline de negociación

## 1) Mapa de archivos de latencia y timing (source of truth)

### 1.1 Timing por nodo y subcampos (`timing.nodes.*`, `llm_calls`, `normalize_merge_diff_ms`, `gates_ms`)
- `backend/negotiation/telemetry/trace_runtime.py`
  - `init_trace_runtime()` define estructura base de nodos y `llm_calls`.
  - `_default_node_timing()` define `total_ms`, `gates_ms`, `normalize_merge_diff_ms`, `llm_ms`, `entered`, `skipped`.
  - `start_node_timer()`/`finish_node_timer()` miden `total_ms` por nodo.
  - `record_node_phase_ms()` acumula subfases (`gates_ms`, `normalize_merge_diff_ms`, `llm_ms`).
  - `record_llm_call()`/`record_llm_call_ms()` añaden entradas a `llm_calls` y acumulan `llm_ms`.
- `backend/negotiation/negotiation_graph.py`
  - `_instrumented_node()` envuelve cada nodo y aplica `start_node_timer` + `finish_node_timer`.
  - `run_negotiation_agent()` añade `t_turn_start`, `t_before_graph`, `t_after_graph`, `t_reply_saved`, `t_summary_enqueued` a `debug_trace`.
- `backend/negotiation/nodes/world_node.py`
  - `record_node_phase_ms(..., "gates_ms", ...)` mide gate de world.
  - `record_node_phase_ms(..., "normalize_merge_diff_ms", ...)` envuelve TODO el bloque skip/merge/diff de world.
  - `record_llm_call_ms(..., name="world_judge_llm")` registra latencia LLM del judge.
  - `record_llm_call_ms(..., name="advisor_llm")` opcional si advisor está habilitado.
- `backend/negotiation/nodes/planner_node.py`
  - `record_llm_call(..., name="planner_llm")` registra llamada del planner.
- `backend/negotiation/nodes/executor_node.py`
  - `record_llm_call(..., name="executor_llm")` registra llamada del executor.

### 1.2 Instrumentación LLM (wrappers y puntos de invocación)
- `backend/negotiation/state/deps.py`
  - `AgentDeps.execute`, `plan_phase_policy`, `update_belief_state` como puntos de inyección.
  - `_default_execute()` llama `get_executor_llm().invoke(messages)`.
- `backend/negotiation/phase_policy_planner.py`
  - `plan_phase_policy()` usa `get_planner_llm().with_structured_output(...).invoke(messages)`.
  - Devuelve `planner_latency_ms`, `planner_failed`, etc. (sin tokens/modelo).
- `backend/negotiation/nodes/world_node.py`
  - `world_judge_llm()` usa `get_planner_llm().invoke(messages)` y retorna `judge_latency_ms`.
- `backend/negotiation/extractors/world_extractor_v4.py`
  - `extract_world_patch_llm_v4()` llama `deps.llm.invoke(messages)` o `deps.execute(messages)`.
  - **No** hay `record_llm_call*` específico para este extractor; por eso en trazas aparece el judge como `world_judge_llm` pero no el extractor como llamada separada.

### 1.3 Construcción de payload LiveTrace (serialización, snapshots, diffs)
- `backend/negotiation/negotiation_graph.py`
  - Construye entrada `debug_trace` completa por turno con `world_prev/world_new/world_diff`, `belief_prev/belief_new/belief_diff`, `trace_runtime` y gran cantidad de metadatos.
  - `diff_belief_state(...)` para diff belief, `top_evidence_v2(...)`, normalizaciones de salida.
- `backend/negotiation/world_state_updater.py`
  - `diff_world_state(prev, new)` crea diff de dominio (`world_buckets`, `world_state_meta`) con objetos `before/after` completos.
- `backend/negotiation/telemetry/live_trace.py`
  - `build_trace_event(...)` transpila `debug_trace` a evento SSE final.
  - `_timing_payload(...)` produce `timing.turn_total_ms`, `timing.timeline`, `timing.nodes`, `timing.llm_calls`.
- `backend/app.py`
  - `_trace_sse_generator()` emite cada evento con `json.dumps(event, ensure_ascii=False)` por SSE.

## 2) Diagrama end-to-end del timeline real

Flujo real de medición:
1. `run_negotiation_agent()` arranca `t_turn_start = perf_counter()`.
2. Normaliza estado de entrada y crea `graph_state` con `trace_runtime` vacío.
3. `t_before_graph` justo antes de `negotiation_app.invoke(graph_state)`.
4. Grafo ejecuta nodos en secuencia:
   - `world_updater` (gate -> update/skip -> diff -> judge)
   - `belief_updater`
   - `policy_progress`
   - `phase_policy_planner`
   - `progress_updater`
   - `executor`
5. `t_after_graph` al salir del grafo.
6. Guarda respuesta (`t_reply_saved`) y encola summary (`t_summary_enqueued`).
7. Persistencia en `debug_trace` y luego LiveTrace deriva `turn_total_ms = (t_summary_enqueued - t_turn_start)`.

Diagrama corto:

`turn_start -> before_graph -> world_updater(gate -> normalize/merge/diff -> world_judge_llm) -> belief_updater -> policy_progress -> phase_policy_planner -> progress_updater -> executor(executor_llm + validator) -> after_graph -> reply_saved -> summary_enqueued`

## 3) Desglose profundo de `world_updater`

Secuencia exacta en `world_updater_node(state)`:
1. Prepara `prev_world`, `gate_state`, features de interacción.
2. Mide gate:
   - `gate_started = perf_counter()`.
   - `gate_world(...)`.
   - `record_node_phase_ms(..., "gates_ms", elapsed)`.
3. Mide bloque `normalize_merge_diff_ms`:
   - `normalize_started = perf_counter()`.
   - Si `world_skipped`: `apply_world_skip_fallback(...)` + `diff_world_state(...)`.
   - Si no skip:
     - `update_world_state(...)`.
     - `diff_world_state(prev_world, new_world)`.
   - `record_node_phase_ms(..., "normalize_merge_diff_ms", elapsed)`.
4. Llama `world_judge_llm(...)` (otra LLM) y registra `record_llm_call_ms(name="world_judge_llm", latency_ms=judge_latency_ms, ...)`.

Qué contiene `update_world_state(...)` (ruta no-skip):
- `copy.deepcopy(prev_world)` para `base`.
- `normalize_world_buckets(base["world_buckets"])`.
- vuelve a `copy.deepcopy(base)` para `world`.
- `extract_world_patch_llm_v4(...)`:
  - serializa `prev_world_state_json = json.dumps(prev_world_state)` en prompt.
  - invoca LLM extractor.
  - parsea JSON y normaliza ítems.
- `merge_world_buckets_append_mostly(...)`:
  - **otro** `copy.deepcopy(prev_world)` interno.
  - normalización por ítem, dedupe por key, sorting y truncado por bucket.
- normalización final de buckets + cálculo de `diff_paths = sorted(_flatten_paths(diff_world_state(base, world)))`.

Conclusión técnica: `normalize_merge_diff_ms` no sólo “normaliza/mergea/diffea”; actualmente también incluye parte LLM del extractor y varias copias profundas/normalizaciones/diffs dentro del mismo bloque temporal.

## 4) Investigación específica: `normalize_merge_diff_ms` (3–4s)

### 4.1 Origen exacto
Medición definida en `world_node.py`:
- Start: antes del `if world_skipped`.
- End: justo después de `update_world_state`/`apply_world_skip_fallback` + `diff_world_state` + metadatos.

Por tanto incluye:
- `update_world_state(...)` completo (incluyendo llamada LLM extractor), o fallback skip.
- `diff_world_state(prev_world, new_world)` externo.

En `update_world_state(...)` incluye además:
- 2+ `copy.deepcopy`.
- múltiples normalizaciones (`normalize_world_buckets`, `_normalize_bucket_item`).
- diff adicional para `diff_paths` (`diff_world_state(base, world)` + `_flatten_paths`).
- serialización JSON completa de `prev_world_state` para prompt extractor.

### 4.2 Hipótesis con verificación

A) **Diff estructural caro**
- Qué buscar: librerías tipo DeepDiff.
- Evidencia: no hay `DeepDiff` en repo; diff implementado es comparaciones directas de dicts (`diff_world_state`).
- Cómo demostrar: timer interno `diff_world_state_ms` (externo e interno) y contador de tamaño `len(json.dumps(prev/new))`.

B) **Copias profundas grandes (`deepcopy`)**
- Qué buscar: `copy.deepcopy` en ruta world.
- Evidencia: hay `deepcopy` en `update_world_state` (base/world) y en `merge_world_buckets_append_mostly`.
- Cómo demostrar: envolver cada deepcopy con `t0=perf_counter`; registrar `world_deepcopy_ms`.

C) **JSON para LiveTrace / prompts**
- Qué buscar: `json.dumps` en world path.
- Evidencia: `extract_world_patch_llm_v4` serializa todo `prev_world_state_json`; LiveTrace SSE serializa evento completo en `app.py`.
- Cómo demostrar: timer en `json.dumps(prev_world_state)` + timer en `json.dumps(event)` en SSE con `event_bytes`.

D) **Normalización/merge de listas**
- Qué buscar: loops por bucket + sorting + dedupe.
- Evidencia: `merge_world_buckets_append_mostly` recorre 7 buckets y hace sort/dedupe en cada uno.
- Cómo demostrar: timer por bucket (`offers_ms`, etc.), `n_existing`, `n_incoming`.

E) **Validación/repair repetida (Pydantic)**
- Qué buscar: validación repetitiva en ruta world.
- Evidencia: en world path actual no se ve Pydantic intenso; hay normalizaciones manuales y dicts.
- Cómo demostrar: profiler de función para confirmar que el costo principal no está ahí.

F) **El diff incluye más de lo que “parece pequeño”**
- Qué buscar: campos completos `before/after` en `world_buckets` y `world_state_meta`.
- Evidencia: `diff_world_state` guarda objetos completos, no patch mínimo.
- Cómo demostrar: registrar bytes de `world_diff` y cardinalidad de listas por bucket.

G) **Trace arma payload grande aunque se muestre poco**
- Qué buscar: `debug_trace.append(...)` con snapshots completos y metadata extensa.
- Evidencia: `negotiation_graph` almacena world/belief base/new/diff completos y múltiples secciones debug; SSE hace `json.dumps(event)` cada emisión.
- Cómo demostrar: medir bytes y latencia de serialización en `build_trace_event` y `app._trace_sse_generator`.

### 4.3 ¿Coste fijo o escalable?
- El bloque `normalize_merge_diff_ms` se ejecuta siempre en `world_updater_node`, incluso en skip (por fallback+diff), porque el timer envuelve ambos caminos.
- En no-skip incluye extractor LLM: costo parcialmente “fijo” de red/modelo + costo local de merges/diffs.
- El diff se computa siempre (`state["world_diff"] = diff_world_state(...)`) también en skip.
- El trace de turno se construye siempre (`debug_trace.append`) y LiveTrace serializa siempre eventos SSE cuando se consultan trazas.

## 5) Desglose de `phase_policy_planner` y `executor`

### Planner
- Cuando corre, su `total_ms` suele ≈ `llm_ms` por el wrapper de nodo + `record_llm_call`.
- `phase_policy_planner_node` hace:
  - gate/skip local (sin LLM).
  - si no skip: `deps.plan_phase_policy(...)`.
- `plan_phase_policy`:
  - compone prompt con múltiples `json.dumps(...)` de resúmenes.
  - usa `with_structured_output(...).invoke(messages)`.
  - parsea `model_dump()` y normaliza policy.
- Conclusión: 8–9s en tus datos es consistente con latencia LLM planner; overhead local existe pero no está segmentado en subfases internas.

### Executor
- `executor_node` mide `llm_started` justo antes de `render_executor_output(...)` y registra `executor_llm` tras retorno.
- `render_executor_output` incluye construcción de prompt + `deps.execute(messages)` + parse JSON.
- Como `total_ms ≈ llm_ms` en tus trazas, el overhead local es bajo comparado con la invocación LLM.
- Falta granularidad: no hay métricas separadas para `prompt_build_ms`, `invoke_ms`, `parse_ms`, `validator_ms`.

## 6) Observabilidad rota: `model/tokens = null`

Dónde debería capturarse:
- `record_llm_call*` acepta `model`, `tokens_in`, `tokens_out`, pero nodos lo pasan en `None`.
- `llm_clients.py` usa `ChatOpenAI`; la respuesta suele traer `response_metadata`/`usage_metadata` según provider.

Parche mínimo propuesto:
1. Añadir helper común `extract_llm_usage(raw)` para leer:
   - `model_name`/`model`.
   - `usage_metadata.input_tokens/output_tokens` o equivalentes.
   - opcional `ttfb_ms`/`queue_ms` si provider los expone.
2. En cada punto de invoke (`world_judge_llm`, `phase_policy_planner.plan_phase_policy`, `_default_execute`, extractor world) capturar `raw` completo (no sólo `content`) y extraer usage.
3. Pasar esos campos a `record_llm_call*`.
4. Extender esquema de `llm_calls` con `queue_ms`/`ttfb_ms` opcionales.

Nota: hoy `record_llm_call` también pone `start_ts`/`end_ts` con `_utc_now_iso()` en el momento de registrar, no los timestamps reales del inicio de llamada. Eso explica timestamps casi idénticos en LiveTrace aunque `latency_ms` sea alto.

## 7) Costes ocultos fuera de `timing.nodes.*`

Evidencia encontrada:
- `debug_trace.append` en `negotiation_graph` construye un objeto muy grande por turno (snapshots completos + debug extras).
- `build_trace_event` hace transformación adicional en cada consulta de trazas.
- `app._trace_sse_generator` serializa cada evento con `json.dumps` por SSE.

No se encontró evidencia de:
- locks de contención relevantes (fuera del lock de carga RAG, no en ruta caliente por turno).
- profiling explícito de GC o métricas de allocs.
- DeepDiff o librerías de diff pesadas.

## 8) Propuestas de mejora P0/P1/P2 (mínimas y medibles)

### P0-1: separar `extractor_llm_ms` de `normalize_merge_diff_ms`
- Archivo/función: `backend/negotiation/nodes/world_node.py`, `update_world_state`.
- Patch mínimo:
  - medir extractor LLM por separado y registrar `record_llm_call_ms(name="world_extractor_llm", node="world_updater", ...)`.
  - mover timer `normalize_merge_diff_ms` para cubrir sólo costo local post-LLM.
- Test recomendado:
  - unit en `test_live_trace_vnext_fields.py` validando nueva llamada LLM.
  - integración en pipeline verificando `world_updater.total_ms ≈ llm_ms(world_extractor+world_judge)+normalize_merge_diff_ms+gates_ms`.
- Métrica esperada:
  - caída fuerte de `normalize_merge_diff_ms` (de ~4s a <<1s si el 80% era extractor).
- Riesgo: bajo; sólo telemetría.

### P0-2: fast-path sin diff completo cuando no hay cambios
- Archivo/función: `world_state_updater.diff_world_state`, `world_node.world_updater_node`.
- Patch mínimo:
  - si `prev_world == world_state`: `world_diff = {}` y evitar `_flatten_paths(diff_world_state(...))`.
- Test:
  - world sin cambios => `diff_paths=[]`, `world_diff={}`.
- Métrica:
  - reducción `normalize_merge_diff_ms` en turnos noop/skip.
- Riesgo: bajo-medio (asegurar contrato downstream que consume `world_diff`).

### P0-3: limitar payload de trace en producción
- Archivo/función: `negotiation_graph.run_negotiation_agent`, `live_trace.build_trace_event`.
- Patch mínimo:
  - flag `TRACE_LEVEL`; en nivel bajo guardar sólo keys cambiadas + hashes en lugar de snapshots `before/after` completos.
- Test:
  - snapshot test de evento en TRACE_LEVEL=1/2.
- Métrica:
  - bytes por evento y `json.dumps(event)_ms`.
- Riesgo: medio (impacta depuración; rollback con flag).

### P1-1: reducir deepcopies en world merge
- Archivo: `world_state_updater.py`.
- Patch mínimo:
  - evitar `copy.deepcopy` redundante en `update_world_state` + `merge_world_buckets_append_mostly` (usar estructura nueva por bucket).
- Test:
  - invariantes de no mutación de `prev_world` + equivalencia funcional.
- Métrica:
  - `world_deepcopy_ms` y latencia total world.
- Riesgo: medio (riesgo de mutación accidental).

### P1-2: diff resumido por bucket
- Archivo: `world_state_updater.diff_world_state`.
- Patch mínimo:
  - guardar sólo campos cambiados y para listas usar resumen (`count_before/after`, top-N items).
- Test:
  - contrato LiveTrace: `world_changed_keys` correcto + payload más chico.
- Métrica:
  - reducción bytes de `world_diff` y SSE.
- Riesgo: medio (herramientas que esperan `before/after` completos).

### P2-1: desacoplar commit de estado y construcción de trace
- Archivo: `negotiation_graph.py` / módulo de telemetry.
- Patch mínimo:
  - persistir estado de negocio primero; construir trace expandido de forma diferida/async o bajo demanda.
- Test:
  - e2e: respuesta no depende del render de trace.
- Métrica:
  - `turn_total_ms` baja en producción; latencia de `/trazas` puede subir levemente.
- Riesgo: medio-alto (arquitectura y orden de persistencia).

### P2-2: perf tests CI
- Archivo nuevo: `backend/tests/perf/test_latency_budget.py` (o script en `backend/scripts`).
- Patch mínimo:
  - benchmark reproducible con mocks de LLM para medir costo local puro.
- Test:
  - budget gates: `world_local_ms` y `trace_build_ms`.
- Riesgo: bajo.

## 9) Plan de experimentos reproducibles

Checklist:
1. Añadir timers internos en world:
   - `extractor_llm_ms`, `deepcopy_ms`, `normalize_ms`, `merge_ms`, `diff_ms`, `flatten_paths_ms`, `json_dump_prev_world_ms`.
2. Añadir tamaños:
   - `prev_world_bytes`, `world_diff_bytes`, `trace_event_bytes`.
3. Ejecutar turno con world pequeño (1-2 offers) y grande (100+ ítems sintéticos).
4. Ejecutar con `TRACE_LEVEL=1` vs `TRACE_LEVEL=3`.
5. Desactivar temporariamente LiveTrace SSE consumidor y comparar.
6. Correr `python -m cProfile` sobre un turno con LLM mockeado para aislar costo CPU local.
7. Verificar hipótesis:
   - si `extractor_llm_ms` ~ `normalize_merge_diff_ms` actual, entonces métrica mezclada era el problema.
   - si `deepcopy_ms + json_dump_ms` domina con LLM mock rápido, optimizar memoria/serialización.
   - si `trace_event_bytes` alto, aplicar resumen de snapshots.

## 10) Checklist final (acción inmediata por ROI)

1. Instrumentar `world_extractor_llm` como llamada LLM explícita.
2. Separar `normalize_merge_diff_ms` en submétricas internas reales.
3. Corregir `start_ts/end_ts` reales en `record_llm_call`.
4. Capturar `model`, `tokens_in`, `tokens_out` desde metadata de respuesta.
5. Medir `json.dumps` en extractor y SSE con bytes.
6. Añadir fast-path `world_diff={}` cuando no cambie estado.
7. Saltar `_flatten_paths(diff(...))` cuando `diff` vacío.
8. Limitar snapshots completos en TRACE_LEVEL bajo.
9. Reducir `deepcopy` redundantes en world merge.
10. Añadir timings finos en planner (`prompt_build`, `invoke`, `parse`).
11. Añadir timings finos en executor (`prompt_build`, `invoke`, `parse`, `validator`).
12. Crear script benchmark local con LLM stub para costo CPU puro.
13. Definir budget de latencia por nodo y alertas.
14. Ejecutar A/B con flags y comparar p50/p95 por campo (`normalize_merge_diff_ms`, `turn_total_ms`).
15. Plan de rollback por feature flags (`TRACE_LEVEL`, `TRACE_INCLUDE_INTERNALS`, nuevos flags de diff resumido).
