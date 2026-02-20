# Diagnóstico post-migración v3 (/negociar)

## Evidencia literal de comandos

### 1) Runtime `/negociar` y wiring
Comando:
```bash
rg -n "@app.post\(\"/negociar\"|run_negotiation_agent\(|workflow.add_node|workflow.add_edge|build_trace_event" backend
```
Extracto literal:
```text
backend/negotiation/telemetry/live_trace.py:43:def build_trace_event(
backend/negotiation/negotiation_graph.py:393:workflow.add_node("world_updater", world_updater_node)
backend/negotiation/negotiation_graph.py:394:workflow.add_node("belief_updater", belief_updater_node)
backend/negotiation/negotiation_graph.py:395:workflow.add_node("policy_progress", policy_progress_node)
backend/negotiation/negotiation_graph.py:396:workflow.add_node("phase_policy_planner", phase_policy_planner_node)
backend/negotiation/negotiation_graph.py:397:workflow.add_node("progress_updater", progress_updater_node)
backend/negotiation/negotiation_graph.py:398:workflow.add_node("executor", executor_node)
backend/negotiation/negotiation_graph.py:400:workflow.add_edge(START, "world_updater")
backend/negotiation/negotiation_graph.py:402:workflow.add_edge("world_updater", "belief_updater")
backend/negotiation/negotiation_graph.py:408:workflow.add_edge("executor", END)
backend/negotiation/negotiation_graph.py:416:def run_negotiation_agent(
backend/app.py:262:@app.post("/negociar", response_model=ChatResponse)
backend/app.py:277:        reply, _ = run_negotiation_agent(state, payload.message)
backend/app.py:308:                event = build_trace_event(
```

### 2) Writers/readers v3 keys
Comando:
```bash
rg -n "world_buckets|world_state_meta|belief_buckets|planner_signals" backend/negotiation backend/app.py backend/tests
```
Extracto literal:
```text
backend/negotiation/world_state_updater.py:238:        world["world_state_meta"]["updated_fields"] = [f"world_buckets.{bucket}" for bucket in updated_buckets]
backend/negotiation/world_state_updater.py:239:        world["world_state_meta"]["updated_buckets"] = updated_buckets
backend/negotiation/world_state_updater.py:213:    base["world_state_meta"]["turn_idx"] = turn_idx
backend/negotiation/belief_state_updater.py:125:        "belief_buckets": merged_buckets,
backend/negotiation/belief_state_updater.py:126:        "planner_signals": planner_signals,
backend/negotiation/nodes/world_node.py:179:            "world_buckets": (world_state or {}).get("world_buckets", {}),
backend/negotiation/nodes/world_node.py:180:            "world_state_meta": (world_state or {}).get("world_state_meta", {}),
backend/negotiation/nodes/belief_node.py:99:    planner_signals = ((belief_state or {}).get("planner_signals") or {}) if isinstance(belief_state, dict) else {}
```

### 3) Scan campos sospechosos
Comando:
```bash
rg -n "\bconfidence\b|turn_idx|updated_fields|updated_buckets|skip_reason|_skipped|gate_enabled|gate_state" backend/negotiation backend/app.py backend/tests
```
Extracto literal:
```text
backend/negotiation/world_state_updater.py:213:    base["world_state_meta"]["turn_idx"] = turn_idx
backend/negotiation/world_state_updater.py:238:        world["world_state_meta"]["updated_fields"] = [f"world_buckets.{bucket}" for bucket in updated_buckets]
backend/negotiation/world_state_updater.py:239:        world["world_state_meta"]["updated_buckets"] = updated_buckets
backend/negotiation/nodes/planner_node.py:257:    planner_meta["planner_skipped"] = planner_skipped
backend/negotiation/nodes/planner_node.py:258:    planner_meta["planner_skip_reason"] = skip_reason
backend/negotiation/nodes/planner_node.py:304:        "skip_reasons": {
backend/negotiation/telemetry/live_trace.py:24:def _gate_choices(gates: dict[str, Any]) -> list[dict[str, Any]]:
backend/tests/test_world_backstop_and_trace_fields.py:30:    assert "world_buckets.offers" in world["world_state_meta"]["updated_fields"]
backend/tests/test_live_trace_telemetry.py:227:    assert choices["belief"]["gate_decision"] == "skipped"
```

### 4) Scan legacy estricto
Comando:
```bash
rg -n "universal_domain|\bnegotiation\b|universal_v2|negotiation_v2|universal_state|open_claims|evidence_items|world_observations|world_derived|intent_" backend/negotiation backend/app.py backend/tests
```
Extracto literal (se detecta únicamente migración/tests/strings de contexto, no en runtime v3 operativo):
```text
backend/tests/test_no_legacy_keys_in_negotiation_runtime.py:6:    "universal_domain",
backend/negotiation/state_migration_v3.py:10:    "universal_domain",
backend/negotiation/state_migration_v3.py:14:    "negotiation_v2",
backend/negotiation/state_migration_v3.py:19:    "world_derived",
```

## Field lifecycle matrix

| key_path | Writers | Readers | Diagnóstico | Acción |
|---|---|---|---|---|
| world_state.world_buckets | `update_world_state` + `merge_world_buckets_append_mostly` | belief updater, planner/render | OK | keep + tests |
| world_state.world_state_meta.turn_idx | `update_world_state` | LiveTrace (world_base/new) + render constraints | Incoherente detectado (no monotónico) | **Fix** monotónico |
| world_state.world_state_meta.updated_fields | `update_world_state` | tests + LiveTrace world diff análisis | Incoherente detectado (pegado por copia superficial + detección por tamaño) | **Fix** deepcopy + diff por contenido |
| world_state.world_state_meta.updated_buckets | `update_world_state` | tests/meta consumidores | Igual que arriba | **Fix** |
| belief_state.belief_buckets | `update_belief_state` | planner/executor/telemetry | OK | keep |
| belief_state.planner_signals | `update_belief_state` | planner/render/telemetry | OK | keep |
| bucket.confidence (world extractor) | extractor + normalización | belief derivation + UI top evidence | Broken-by-default (faltante => 0.0) | **Fix** default 0.6 |
| gates booleanos + skip reasons | `planner_node` (`*_skipped`, `skip_reasons`) | `build_trace_event` + LiveTrace UI | Semántica confusa enabled/skipped | **Fix** separar `gate_enabled`, `gate_decision`, `gate_reason` |

## Diagnóstico de “broken-by-legacy” y correcciones

### A) `turn_idx`
- Causa: `update_world_state` tomaba `turn_count` sin asegurar monotonicidad frente a `prev.turn_idx`.
- Fix v3-first: regla monotónica única: `turn_idx = max(turn_count, prev_turn_idx + 1)` cuando `turn_count` no avanza.

### B) `updated_fields` / `updated_buckets`
- Causa: copia superficial del estado base (`dict(prev_world)`), y además detección de update basada en tamaño del índice (ignoraba cambios de contenido/confidence).
- Fix v3-first: `deepcopy` del estado + comparación `before_items` vs `after` por bucket.

### C) `confidence`
- Decisión: **se mantiene** en contrato v3.
- Causa de rotura: default a `0.0` cuando extractor no entrega `confidence`.
- Fix: fallback a `0.6` en extractor, normalizador y merge world.

### D) gates “enabled vs skipped”
- Causa: `gate_choices.selected` mezclaba semánticas (sobre todo para flags `*_skipped`).
- Fix: nuevo contrato explícito en telemetry/UI por gate: `gate_enabled` (flag/config), `gate_decision` (`executed|skipped`), `gate_reason`.

## Telemetría / LiveTrace
- `build_trace_event` conserva campos útiles v3 y elimina ambigüedad de gates mediante estructura explícita.
- Se mantiene payload de diagnóstico (world/belief base/new/diff) para auditoría de coherencia en runtime.

## Verificación ejecutada
- `pytest -q backend/tests/test_api_negotiation_smoke.py`
- `pytest -q backend/tests/test_live_trace_telemetry.py`
- `pytest -q backend/tests/test_no_legacy_keys_in_negotiation_runtime.py`
- `pytest -q backend/tests/test_state_migration_v3.py`
- `pytest -q backend/tests/test_world_backstop_and_trace_fields.py backend/tests/test_negotiation_v3_post_migration_guards.py`


## Follow-up quirúrgico (post feedback)

### Confidence: semántica corregida (sin falsear 0.0)
Se eliminó el patrón inválido `or 0.6`. Nueva regla aplicada en extractor v4, updater y normalización:
- `raw_conf is None` => default `0.6` + `confidence_defaulted=true`.
- `raw_conf` presente y parseable => clamp 0..1, **sin mínimo artificial** (`0.0` se preserva).
- `raw_conf` presente pero no parseable => default `0.6` + `confidence_defaulted=true`.

Además, el extractor agrega resumen en meta:
- `confidence_defaulted_count`
- `confidence_item_count`

### Alias legacy eliminado
Se eliminó completamente el alias `extract_world_patch_llm_v3`.
Comprobación literal:
```bash
rg -n "extract_world_patch_llm_v3" backend docs
```
Salida: sin ocurrencias.

### LiveTrace base/new turn_idx
Se añadió prueba explícita para garantizar que cuando `turn_idx` avanza, `world_state_meta` queda en `world_changed_keys` y no en `world_unchanged_keys`, preservando `base.turn_idx` anterior y `new.turn_idx` nuevo.
