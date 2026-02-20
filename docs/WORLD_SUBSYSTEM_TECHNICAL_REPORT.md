# Informe técnico EXTREMADAMENTE detallado — subsistema WORLD (`/negociar`)

> Alcance: **solo WORLD** y sus integraciones directas (belief input, policy_plan_judgement, gates, LiveTrace). Todo está basado en código actual del repo.

## 1) MAPA DE ARCHIVOS (source of truth)

1. `backend/negotiation/nodes/world_node.py`  
   Nodo entrypoint de WORLD (`world_updater_node`): aplica gate de world, ejecuta `update_world_state`, calcula `world_diff`, ejecuta `world_judge_llm`, registra telemetría y escribe metadatos de gate/debug.

2. `backend/negotiation/world_state_updater.py`  
   Núcleo de actualización world: normaliza base, llama extractor v4, hace merge append-mostly, normaliza buckets, actualiza `world_state_meta`, y devuelve `(world, meta)`.

3. `backend/negotiation/extractors/world_extractor_v4.py`  
   Prompting + parseo del extractor LLM v4. Incluye `_safe_json_load`, `_normalize_item` y cálculo de `extractor_confidence_summary`.

4. `backend/negotiation/validation.py`  
   Normalización fuerte de buckets/world (`normalize_world_buckets`, `normalize_world_state`) incluyendo dedupe y defaulting de confidence.

5. `backend/negotiation/gating/gate_world.py`  
   Heurística de gate world (`gate_world`): actualmente *siempre refresca* salvo mensaje vacío.

6. `backend/negotiation/gate_utils.py`  
   Re-export de gates/fingerprints usados por nodos (`gate_world`, `state_meta_fingerprint`, etc.).

7. `backend/negotiation/gating/fingerprints.py`  
   Utilidades de fingerprint para world meta/buckets/interacción que alimentan gate state.

8. `backend/negotiation/telemetry/trace.py`  
   `top_evidence_v2(world_state)` (evidencia top por confidence) y diffs de belief.

9. `backend/negotiation/telemetry/trace_runtime.py`  
   Runtime de timings por nodo (`gates_ms`, `normalize_merge_diff_ms`, `llm_ms`) y registro de `llm_calls`.

10. `backend/negotiation/telemetry/live_trace.py`  
    Construcción de evento SSE (`build_trace_event`) y traducción de gates a `gate_choices`.

11. `backend/negotiation/negotiation_graph.py`  
    Wiring del grafo y persistencia de `trace_item` (incluye world_prev/new/diff, extractor summary, top_evidence_v2, gates, trace_runtime).

12. `backend/negotiation/nodes/belief_node.py`  
    Consume `world_state` y `world_diff`; usa fingerprint de world buckets para decidir `belief_skipped`.

13. `backend/negotiation/belief_state_updater.py`  
    Deriva belief desde `world_buckets` (`offers`→`hypotheses`, etc.), confirmando qué parte de WORLD alimenta belief.

14. `backend/negotiation/nodes/policy_progress_node.py` + `backend/negotiation/policy_progress.py`  
    Consumen `policy_plan_judgement` producido por world_judge para mapear `plan_status`→`planner_request`.

15. `backend/negotiation/llm_clients.py`  
    Cliente LLM de world (`get_world_llm`) y planner (`get_planner_llm`, usado por `world_judge_llm`).

16. `backend/tests/test_world_backstop_and_trace_fields.py`  
    Pruebas actuales de merge/dedupe/confidence summary/defaulting.

17. `backend/tests/test_world_judge_always_on.py`  
    Pruebas actuales del schema/degradación de world_judge.

18. `backend/prompts.py`  
    **No encontrado prompt extractor world** aquí; sí hay prompts planner/belief/phase. WORLD extractor usa prompt inline en `world_extractor_v4.py`.

---

## 2) FLOW END-TO-END (SECUENCIA EXACTA)

### 2.1 Entry point del nodo

**Función exacta:** `world_updater_node(state: dict) -> dict` en `backend/negotiation/nodes/world_node.py`.

### 2.2 Lecturas del `state` global (WORLD)

Lee explícitamente:
- `state["deps"]`
- `state["world_state"]` (prev world)
- `state["progress_state"]` y `progress_state["gate_state"]`
- `state["user_message"]`, `state["turn_count"]`, `state["input_modality"]`
- `state["recent_history"]`/`state["recent_history_text"]`
- `state["belief_state"]` (solo para pasar a update_world_state)
- `state["objective"]` (para world_judge)

### 2.3 Decisión de `world_skipped`

Se decide en `gate_world(...)` (archivo `gating/gate_world.py`):

```python
if not (user_message or "").strip():
    return True, "empty_message", {"extractor_mode": "none"}
...
return False, "always_refresh_user_turn", change_meta
```

**Heurística real hoy:**
- `world_skipped=True` solo si mensaje vacío.
- En cualquier mensaje no vacío: `world_skipped=False`, razón `always_refresh_user_turn`.

### 2.4 Camino normal (no skip)

1. `update_world_state(prev_world, user_message, recent_history, belief_state, turn_count, conversation_mode, deps)`.
2. `update_world_state`:
   - deep copy base + `ensure_world_buckets` + `normalize_world_buckets`.
   - fija `turn_idx` monotónico (`prev_turn_idx + 1` cuando `turn_count <= prev_turn_idx`).
   - resuelve `llm_deps` (usa `deps.llm` o `get_world_llm()`).
   - llama `extract_world_patch_llm_v4(...)`.
   - merge patch con `merge_world_buckets_append_mostly(...)`.
   - normaliza buckets otra vez (`normalize_world_buckets`).
   - llena `world_state_meta` (`last_update_source`, `updated_fields`, `updated_buckets`, `extractor_failed`, `error`).
   - calcula `diff_paths` usando `_flatten_paths(diff_world_state(base, world))`.
   - retorna `world, meta`.
3. `world_updater_node` calcula `state["world_diff"] = diff_world_state(prev_world, world_state)`.
4. Ejecuta `world_judge_llm(...)` con `active_plan`, `user_message`, `objective`, `world_state`, `recent_history`, `turn_count`.
5. Escribe `state["policy_plan_judgement"]` y mete judge meta en `state["extractor_meta"]["world_judge_meta"]`.
6. Actualiza fingerprints y estado de gate (`world_meta_fingerprint_prev`, `input_shape_prev`, etc.).

### 2.5 Camino skip

Si `world_skipped=True`:
- Llama `apply_world_skip_fallback(prev_world, user_message, turn_count)`.
- Reescribe `state["world_state"]` normalizado, mantiene buckets previos.
- Igual calcula `world_diff`.
- `extractor_meta` marca `extractor_skipped=True`, `skip_reason`, `extractor_used=False`.
- **Aun así corre `world_judge_llm`** (siempre-on).

### 2.6 Escrituras del `state` global (WORLD)

Escribe:
- `prev_world_state`
- `world_state`
- `world_diff`
- `extractor_meta`
- `policy_plan_judgement`
- `world_debug`
- `progress_state` (conversation mode + gate state)

---

## 3) PROMPTS EXACTOS A LA LLM (EXTRACTOR)

Archivo: `backend/negotiation/extractors/world_extractor_v4.py`.

### 3.1 SYSTEM prompt exacto

```text
You are a strict JSON extractor for negotiation world buckets.
Return ONLY valid JSON.
No markdown. No extra keys.
Do not invent numbers or dates.
```

### 3.2 USER prompt exacto (template)

```text
Update WORLD in append-mostly mode.

conversation_mode: {conversation_mode}
turn_idx: {turn_idx}

CURRENT user_message:
{user_message}

PREVIOUS world_state (json):
{prev_world_state_json}

RULES:
- Output ONLY this JSON schema:
{
  "schema_version": "world_extractor_v4",
  "world_buckets_patch": {
    "offers": [item],
    "concessions": [item],
    "constraints": [item],
    "interests": [item],
    "claims": [item],
    "requests": [item],
    "context": [item]
  },
  "meta": {
    "negotiation_signal_detected": true|false,
    "extraction_quality": "high|medium|low"
  }
}

item format:
{
  "text": "short human sentence useful for a planner",
  "confidence": 0.85,
  "raw_text": "literal quote from user message",
  "source_turn": {turn_idx}
}

- Append-mostly: propose only NEW items from this user message.
- Do not rewrite prior items.
- If user expresses a conditional/implicit exchange, add at least one item in offers or concessions.
- Keep text simple and concise.
- raw_text is mandatory for every emitted item.
- confidence is mandatory and must be numeric in [0,1].
- Use confidence >= 0.60 for emitted items; if confidence would be < 0.60, do not emit that item.
- Never emit confidence=0 unless the quote explicitly states total uncertainty.
- If no new information for a bucket, return empty list for that bucket.
```

### 3.3 Variables interpoladas

Se interpolan exactamente:
- `{conversation_mode}`
- `{turn_idx}`
- `{user_message}`
- `{prev_world_state_json}`

**No se pasa history al extractor** (solo `prev_world_state` + `user_message`). `belief_state` llega por firma pero se descarta con `del belief_state`.

### 3.4 Wrapper/modelo y timing

- Invocación extractor: `deps.llm.invoke(messages)` si `deps` trae `.llm`, o `deps.execute(messages)` si no.
- `update_world_state` construye `llm_deps` con `get_world_llm()` por defecto.
- `world_updater_node` **no registra llm_call del extractor** en `trace_runtime`; solo registra `world_judge_llm` con `record_llm_call_ms(...)`.
- Resultado: `timing.nodes.world_updater.llm_ms` hoy refleja mayormente judge, no extractor + judge por separado (evidencia en tus trazas).

---

## 4) OUTPUT DE LA LLM (SCHEMA REAL)

### 4.1 Schema esperado (extractor)

```json
{
  "schema_version": "world_extractor_v4",
  "world_buckets_patch": {
    "offers": [],
    "concessions": [],
    "constraints": [],
    "interests": [],
    "claims": [],
    "requests": [],
    "context": []
  },
  "meta": {
    "negotiation_signal_detected": false,
    "extraction_quality": "medium"
  }
}
```

### 4.2 Ejemplo mínimo válido

```json
{
  "schema_version": "world_extractor_v4",
  "world_buckets_patch": {
    "offers": [],
    "concessions": [],
    "constraints": [],
    "interests": [],
    "claims": [],
    "requests": [],
    "context": []
  },
  "meta": {}
}
```

### 4.3 Ejemplo completo (todos buckets)

```json
{
  "schema_version": "world_extractor_v4",
  "world_buckets_patch": {
    "offers": [{"text":"Sube hoy si incluye ITV","confidence":0.82,"raw_text":"si me pagas más hoy, yo te pago la ITV 2 años","source_turn":3}],
    "concessions": [{"text":"Asume ITV 2 años","confidence":0.8,"raw_text":"yo te pago la ITV 2 años","source_turn":3}],
    "constraints": [{"text":"Necesita liquidez inmediata","confidence":0.7,"raw_text":"más hoy","source_turn":3}],
    "interests": [{"text":"Maximizar pago inmediato","confidence":0.72,"raw_text":"me pagas más hoy","source_turn":3}],
    "claims": [{"text":"Dice poder cubrir ITV dos años","confidence":0.66,"raw_text":"yo te pago la ITV 2 años","source_turn":3}],
    "requests": [{"text":"Pide pago más alto hoy","confidence":0.75,"raw_text":"si me pagas más hoy","source_turn":3}],
    "context": [{"text":"Negociación en fase de intercambio condicional","confidence":0.62,"raw_text":"si ... yo ...","source_turn":3}]
  },
  "meta": {
    "negotiation_signal_detected": true,
    "extraction_quality": "high"
  }
}
```

### 4.4 Parseo real

- `_safe_json_load(text)` recorta desde primer `{` hasta último `}` y hace `json.loads`.
- No `with_structured_output` en extractor world.
- No retries explícitos de extractor en `update_world_state`.

### 4.5 Errores/fallbacks

- Si extractor lanza excepción: `update_world_state` marca `world_state_meta.extractor_failed=True`, `world_state_meta.error`, retorna world normalizado sin patch aplicado.
- Si world gate skip: `apply_world_skip_fallback` marca `extractor_skipped=True` (pero `fallback_applied=False`, no inyecta contenido nuevo).
- Retries extractor: **no encontrado**.

---

## 5) NORMALIZACIÓN, DEFAULTING Y VALIDACIÓN

| Función | Archivo | Qué corrige | Cuándo se ejecuta | Riesgos de bug |
|---|---|---|---|---|
| `_normalize_item` | `extractors/world_extractor_v4.py` | Valida dict, exige `text`+`raw_text`, default/confidence clamp, source_turn int, flags `confidence_defaulted/source` | Al procesar output LLM crudo | Si LLM manda raw_text casi vacío repetidamente, se descarta y se pierde señal válida |
| `_normalize_bucket_item` | `world_state_updater.py` | Re-normaliza items ya mergeables, defaulting de confidence, source_turn, confidence_source | En merge de prev+patch | Doble normalización puede ocultar origen real (`emitted_by_llm`→`defaulted_by_normalizer`) |
| `normalize_world_buckets` | `validation.py` | Dedupe por `raw_text` normalizado, trim de texto, confidence clamp/defaulting, max_items | Antes y después del merge + en skip fallback | Parafrasis con raw_text distinto no se dedupean; crece ruido semántico |
| `ensure_world_buckets` | `world_state_updater.py` | Garantiza keys de buckets | Inicio de update/merge/skip | Si código externo agrega bucket nuevo, se pierde en esta función |
| `normalize_world_state` | `validation.py` | Estabiliza schema_version/meta/updated lists | Al salir del grafo (persistencia) | Campos meta extra pueden no preservarse si no están en allowlist |
| `_normalize_text` | `world_state_updater.py` | lower + sin acentos + collapse spaces | Dedupe key | Dedupe agresivo de frases similares puede mezclar matices |

Notas concretas de confidence:
- Missing/invalid/`<=0` -> `0.6` en extractor y normalizers.
- `confidence=0` no-defaulted queda bloqueado por normalización (se vuelve 0.6 y `confidence_defaulted=true`).
- Cubierto por tests (`test_world_backstop_and_trace_fields.py`, `test_confidence_guardrails_v3.py`).

---

## 6) MERGE + DEDUPE (ALGORITMO EXACTO)

### 6.1 Función de merge

`merge_world_buckets_append_mostly(prev_world, patch, turn_idx, max_items=8)` en `world_state_updater.py`.

### 6.2 Dedupe key

`_bucket_dedupe_key(item)`:
1. usa `raw_text` normalizado (`_normalize_text`).
2. fallback a `text` normalizado si raw_text vacío.

### 6.3 Winner

Si key ya existe:
- reemplaza solo si `incoming.confidence > existing.confidence`.
- empate de confidence mantiene previo (no reemplazo por recencia).

### 6.4 Comportamiento por bucket

- Todos los buckets siguen append-mostly + dedupe.
- Resultado se ordena por confidence desc + source_turn desc (en `_sort_bucket_items`) y se recorta a `max_items=8`.
- No overwrite total de bucket (salvo efecto de dedupe+recorte).

### 6.5 Casos especiales

- Sin raw_text: item puede sobrevivir vía fallback a `text` en merge updater, pero **en extractor `_normalize_item` raw_text es obligatorio** y allí se filtra.
- Casi igual/paráfrasis (raw_text distinto): se consideran diferentes -> ambos quedan si caben en top8.

### 6.6 Complejidad/hotspots

- Por bucket: O(n + m) construir índice + O(k log k) ordenado final, k<=n+m.
- Hotspot real de latencia no parece CPU: tus trazas muestran world_updater en segundos, lo dominante es LLM/judge y no loops de merge.

---

## 7) GENERACIÓN DE `world_diff`

### 7.1 Dónde

`diff_world_state(prev, new)` en `world_state_updater.py`.

### 7.2 Qué representa hoy

Devuelve:
```json
{
  "domain": {
    "world_buckets": {"before": ..., "after": ...},
    "world_state_meta": {"before": ..., "after": ...}
  }
}
```

Solo compara dos claves tracked:
- `world_buckets`
- `world_state_meta`

### 7.3 Ejemplo before/after/diff

Coincide con tu LiveTrace: al añadir oferta y subir `turn_idx`, diff incluye cambios en `world_buckets` y `world_state_meta`.

### 7.4 `no_world_delta`

String `no_world_delta` no sale del gate world. En práctica aparece en gate belief/planner cuando su lógica no detecta cambio material. Para world gate no aplica porque gate_world casi siempre refresca.

Fiabilidad para “nueva info”:
- `diff_world_state` sí detecta cambio estructural.
- Pero world_judge **no consume `world_diff` explícito**; consume snapshot world_state + plan + user_message. Ahí puede perder sensibilidad a “added offer”.

---

## 8) WORLD JUDGE (`policy_plan_judgement`)

### 8.1 Dónde se llama

`world_updater_node` llama `world_judge_llm(...)` inmediatamente después de actualizar world.

### 8.2 Prompt usado

`_WORLD_JUDGE_SYSTEM_PROMPT` en `nodes/world_node.py`, schema v1 con campos:
- `plan_presence`, `plan_id`, `evaluated_step_idx`, `plan_status`, `why`, `evidence`, `confidence`, `missing_signals`, `safety_flags`, `degraded`, `degrade_reason`.
- Regla dura: `advance_step/completed` requieren `evidence` no vacía.

### 8.3 Inputs exactos de judge

Payload (HumanMessage JSON):
- `turn_idx`
- `objective`
- `active_plan`
- `current_step`
- `user_message`
- `recent_history`
- `world_state_summary` (`world_buckets`, `world_state_meta`)

### 8.4 Schema esperado salida

Normalizado por `_normalize_judgement(...)`:
- plan_status limitado a `{continue_same_step, advance_step, completed, interrupted_replan}`.
- confidence clamped [0..1].
- evidence truncada a 4.
- missing/safety truncados.
- si `advance/completed` y `evidence=[]` -> fuerza `continue_same_step`, `degraded=true`, `degrade_reason=missing_evidence_for_progress`.

### 8.5 Manejo evidence/missing_signals

- Evidence la emite LLM; no hay verificación semántica contra diff.
- missing_signals lo emite LLM; backend solo tipa/trunca.

### 8.6 Degradación

- Excepción LLM -> `_fallback_judgement(...)` (`degraded=true`, con/no plan según active_plan).
- `judge_meta` incluye `judge_error_type`, `judge_retry_count`, `judge_latency_ms`, `judge_degraded`.

### 8.7 Consumo en policy_progress_node

`policy_progress_node` -> `update_policy_state(...)` mapea:
- `continue_same_step` -> `planner_request=continue_policy`
- `advance_step` -> `continue_policy` + `advance_step=true`
- `completed` -> `replan_policy`
- missing/invalid -> `interrupted_replan` -> `replan_policy`

Este mapeo explica tu caso: judge dijo continue_same_step ⇒ planner_request continue_policy ⇒ planner skipped (reason `continue_policy`).

---

## 9) GATES DE WORLD

### 9.1 Heurística exacta

`gate_world` actualmente no usa intervalos ni cambios de fingerprints para saltar; siempre refresca en input no vacío.

### 9.2 Reporte en `gate_meta` y `gate_choices`

- `planner_node` compone:
```python
{"world_skipped": extractor_meta.extractor_skipped, ...}
```
- LiveTrace `_gate_choices` traduce bools a:
  - `gate_enabled=true`
  - `gate_decision=executed|skipped`
  - `gate_reason=skip_reasons[gate]`

### 9.3 Coherencia con `timing.nodes.world_updater.skipped`

- `_instrumented_node` marca skipped con `gate_meta["world_skipped"]`.
- **Riesgo actual:** `gate_meta` se escribe recién en planner_node; `finish_node_timer` de world_updater corre antes. Por eso `world_updater.skipped` en timing puede no reflejar el estado final del gate world.
- En tus trazas world_updater `skipped=false` consistente porque world casi nunca skip; pero wiring es frágil.

---

## 10) TELEMETRÍA / LIVETRACE PARA WORLD

### 10.1 Campos derivados de WORLD

1. `world_base/world_new/world_diff`  
   Armados en `negotiation_graph.py` al append de `state.debug_trace`.

2. `world_changed_keys/world_unchanged_keys`  
   Derivados en `live_trace.build_trace_event` con `_changed_unchanged`.

3. `top_evidence_v2`  
   Calculado en `negotiation_graph.py` con `telemetry.trace.top_evidence_v2(new_world_state)`.

4. `extractor_confidence_summary`  
   Propagado desde `extractor_meta` a trace_item y luego a LiveTrace.

5. `timing.nodes.world_updater` (`gates_ms`, `normalize_merge_diff_ms`, `llm_ms`)  
   `gates_ms` y `normalize_merge_diff_ms` se registran en `world_updater_node`. `llm_ms` viene de `record_llm_call_ms` (judge).

### 10.2 Consistencia (observación importante)

- En tus trazas, `world_updater.llm_ms` coincide con `world_judge_llm.latency_ms`; extractor LLM no aparece como llamada separada.
- `normalize_merge_diff_ms` sale muy alto (3-4s), lo que sugiere que incluye parte del tiempo extractor por cómo se toma la ventana temporal en node (empieza antes del update completo).

---

## 11) PROBLEMAS OBSERVADOS + HIPÓTESIS (BASADO EN TU TRACE)

Caso: se agrega oferta nueva en `world_buckets.offers`, pero judge dice “no new info verificable”, `evidence=[]`, `continue_same_step`, planner skip.

### 11.1 Por qué puede pasar (causas probables por código)

1. **Judge no usa `world_diff` explícito**, solo snapshot world + texto. Puede interpretar que la nueva oferta no satisface el criterio del step activo (`nueva_informacion_verificable`) aunque sí haya delta estructural.

2. **No hay invariante backend** que fuerce coherencia “si `updated_buckets` incluye offers con item nuevo, no permitir `evidence=[]` en continue_same_step por falta de info”.

3. **Plan-step success criteria** del plan activo puede no mapear bien a ofertas de intercambio; judge queda demasiado literal y conservador.

4. **Planner skip por diseño**: `continue_same_step` lleva a `planner_request=continue_policy`; en planner node eso activa fast-path skip.

### 11.2 Evidencia concreta en tu trace

- `world_diff.domain.world_buckets.before!=after` (nueva oferta presente).
- `top_evidence_v2` muestra dos ofertas (0.85).
- `policy_plan_judgement.evidence=[]` + `missing_signals=["nueva_informacion_verificable"]`.
- `planner_meta.planner_skipped=true`, reason `continue_policy`.

### 11.3 Detección automática recomendada

Regla detectable en runtime:
- Si `world_state_meta.updated_buckets` contiene `offers|concessions|constraints|requests` **y** `policy_plan_judgement.plan_status==continue_same_step` **y** `evidence=[]` **y** `missing_signals` contiene `nueva_informacion_verificable`, generar flag de inconsistencia (`judge_world_delta_conflict=true`) en trace.

---

## 12) PROPUESTAS DE PULIDO (P0/P1/P2)

## P0 — Invariantes de coherencia judge vs world delta

### Cambio P0.1
- **Impacto:** alto (evita falsos “no new info”).
- **Riesgo:** bajo-medio.
- **Dónde tocar:** `backend/negotiation/nodes/world_node.py` (`world_updater_node`, post judge).

**Patch mínimo (pseudocódigo):**
```python
updated_buckets = set((state.get("world_state", {}).get("world_state_meta", {}).get("updated_buckets", [])))
judgement = state["policy_plan_judgement"]
if updated_buckets & {"offers","concessions","constraints","requests"}:
    if judgement.get("plan_status") == "continue_same_step" and not judgement.get("evidence"):
        judgement["degraded"] = True
        judgement["degrade_reason"] = "world_delta_without_evidence"
        judgement["missing_signals"] = list(set(judgement.get("missing_signals", [])) | {"judge_alignment_needed"})
```

**Test recomendado:**
- Nuevo test en `backend/tests/test_world_judge_always_on.py` o `test_world_backstop_and_trace_fields.py` que simule delta en offers + judge output vacío y verifique `degrade_reason=world_delta_without_evidence`.

**Métrica:**
- `% turns con world_delta_without_evidence` (debe tender a 0 tras ajustar prompt/model).

### Cambio P0.2
- **Impacto:** alto (telemetría confiable de costos).
- **Riesgo:** bajo.
- **Dónde tocar:** `world_state_updater.update_world_state` + `world_node.world_updater_node` + `trace_runtime`.

**Patch mínimo:** registrar llamada extractor como `world_extractor_llm` con `record_llm_call_ms` y latencia real.

**Test recomendado:**
- test de telemetry que valide `timing.llm_calls` contiene `world_extractor_llm` y `world_judge_llm` en nodo world_updater.

**Métrica:**
- latencia separada extractor vs judge p50/p95.

### Cambio P0.3
- **Impacto:** alto (consistencia de `timing.nodes.world_updater.skipped`).
- **Riesgo:** bajo.
- **Dónde tocar:** `_instrumented_node` en `negotiation_graph.py` o `world_updater_node`.

**Patch mínimo:**
- decidir skip con campo ya existente al final del nodo (`extractor_meta.extractor_skipped`) en vez de depender de `gate_meta` (que se llena después).

**Test recomendado:**
- escenario mensaje vacío => world skip true y `timing.nodes.world_updater.skipped == true`.

---

## P1 — Dedupe/merge y diff más informativos

### Cambio P1.1 (paráfrasis)
- **Impacto:** medio-alto.
- **Riesgo:** medio.
- **Dónde tocar:** `world_state_updater._bucket_dedupe_key` o paso previo al merge.

**Idea mínima segura:** mantener key primaria por raw_text, pero añadir key secundaria opcional por `text` normalizado + bucket para detectar near-duplicate y marcar `meta.duplicate_semantic_candidate_count` (sin dedupe destructivo todavía).

**Test:**
- dos ofertas parafraseadas con raw_text distinto -> ambas se conservan, pero contador semantic duplicate >0.

### Cambio P1.2 (diff estructural)
- **Impacto:** alto para judge/gates.
- **Riesgo:** medio.
- **Dónde tocar:** `world_state_updater.diff_world_state`.

**Patch mínimo:** añadir sección `bucket_delta_summary`:
```json
{"offers":{"added":1,"removed":0,"changed":0}, ...}
```

**Test:**
- before/after del caso ITV debe reportar `offers.added=1`.

### Cambio P1.3 (judge prompt grounding)
- **Impacto:** alto.
- **Riesgo:** medio.
- **Dónde tocar:** `_WORLD_JUDGE_SYSTEM_PROMPT` + payload en `world_judge_llm`.

**Patch mínimo:** incluir `world_diff` o `updated_buckets` en payload y regla:
- “si hay added en offers/concessions/constraints/requests, evidence no puede ser vacía”.

**Test:**
- fixture donde diff añade offer y modelo devuelve continue sin evidence -> normalizador o guard rail lo corrige/degrada.

---

## P2 — Refactors/limpieza

### Cambio P2.1
- **Impacto:** medio.
- **Riesgo:** bajo.
- **Dónde:** extraer contrato `WorldJudgeDecision` en schema typed para no depender de dicts abiertos.

### Cambio P2.2
- **Impacto:** medio.
- **Riesgo:** bajo.
- **Dónde:** unificar defaulting confidence en una sola utilidad compartida (evitar divergencia extractor vs validation).

### Cambio P2.3
- **Impacto:** medio.
- **Riesgo:** bajo.
- **Dónde:** enriquecer `extractor_meta` con `patch_counts_by_bucket` y `merge_counts_by_bucket` para auditoría rápida.

---

## 13) CHECKLIST FINAL (qué hago mañana)

1. [P0] Añadir guard-rail `world_delta_without_evidence` en `world_updater_node`.
2. [P0] Registrar `world_extractor_llm` en `trace_runtime.llm_calls`.
3. [P0] Corregir coherencia de `timing.nodes.world_updater.skipped`.
4. [P0] Crear test unitario del caso real ITV (world delta + judge inconsistente).
5. [P0] Crear alerta LiveTrace cuando `world_changed && evidence=[] && continue_same_step`.
6. [P1] Extender `diff_world_state` con `bucket_delta_summary`.
7. [P1] Pasar `world_diff`/`updated_buckets` explícito al payload de `world_judge_llm`.
8. [P1] Ajustar prompt judge con regla dura de evidence cuando hay delta material.
9. [P1] Añadir métricas p50/p95 separadas: extractor vs judge.
10. [P1] Añadir contador de posibles duplicados semánticos de offers/concessions.
11. [P2] Unificar utilidades de defaulting confidence.
12. [P2] Tipar contrato de `policy_plan_judgement` en schemas.
13. [P2] Limpiar metadatos world para distinguir claramente parse/merge/normalize timings.

---

## Comandos concretos usados para construir este informe

```bash
rg -n "world_updater_node|world_judge_llm|update_world_state|extract_world_patch_llm_v4|merge_world_buckets_append_mostly|diff_world_state" backend/negotiation -g '*.py'
rg -n "gate_world|world_skipped|state_meta_fingerprint|world_buckets_fingerprint" backend/negotiation -g '*.py'
rg -n "extractor_confidence_summary|top_evidence_v2|build_trace_event|trace_runtime|gate_choices" backend/negotiation -g '*.py'
rg -n "world_judge|confidence_defaulted|update_world_state|merge_world_buckets_append_mostly" backend/tests -g '*.py'
```

Si quieres, en el siguiente paso te puedo entregar un **patch concreto P0** (código + tests) para cerrar el caso ITV sin rediseñar nada.
