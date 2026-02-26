# V02 — LiveTrace2 ledger hash observability

## A) Qué se afirma que cambió
- Se agregaron hashes de ledger para planner/executor/effective.
- Se calcula `ledger_mismatch_detected` como señal observacional (no gate).
- Los campos se exponen en `debug_trace` y en el modelo de evento LiveTrace2.

## B) Dónde está en el repo (rutas + símbolos)
- `backend/negotiation/nodes/executor_node.py`
  - `state["ledger_observability"]`
- `backend/negotiation/negotiation_graph.py`
  - append de hashes a `state.debug_trace`
- `backend/negotiation/telemetry/live_trace2.py`
  - `planner_ledger_hash`, `executor_ledger_hash`, `effective_ledger_hash`, `ledger_mismatch_detected`
- `backend/tests/test_semantic_runtime_v1.py`
  - `test_trace_exposes_ledger_hash_observability`

## C) Evidencia 1 — Diff / Snippets (con contexto)
```python
# backend/negotiation/nodes/executor_node.py
state["ledger_observability"] = {
    "planner_ledger_hash": planner_hash,
    "executor_ledger_hash": executor_hash,
    "effective_ledger_hash": effective_hash,
    "ledger_mismatch_detected": bool(planner_hash and executor_hash and planner_hash != executor_hash),
}
```

```python
# backend/negotiation/negotiation_graph.py
"planner_ledger_hash": new_graph_state.get("planner_ledger_hash", ""),
"executor_ledger_hash": new_graph_state.get("executor_ledger_hash", ""),
"effective_ledger_hash": new_graph_state.get("effective_ledger_hash", ""),
"ledger_mismatch_detected": ...
```

```python
# backend/negotiation/telemetry/live_trace2.py
"planner_ledger_hash": str(payload.get("planner_ledger_hash") or ""),
"executor_ledger_hash": str(payload.get("executor_ledger_hash") or ""),
"effective_ledger_hash": str(payload.get("effective_ledger_hash") or ""),
"ledger_mismatch_detected": bool(payload.get("ledger_mismatch_detected", False)),
```

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "planner_ledger_hash|executor_ledger_hash|effective_ledger_hash|ledger_mismatch_detected" backend/negotiation
```
Debe mostrar wiring en executor node, negotiation graph y live_trace2.

## E) Evidencia 3 — Runtime / Prompt rendering (si aplica)
- No aplica prompt render directo; aplica runtime trace.
- Test `test_trace_exposes_ledger_hash_observability` valida que los tres hashes existen y que planner==executor.

## F) Evidencia 4 — Telemetría / LiveTrace2
- Los campos se agregan en el modelo final `build_semantic_turn_model` y quedan serializables para LiveTrace2.
- `ledger_mismatch_detected` no controla flujo; es diagnóstico.

## G) Qué podría estar mal / riesgos detectados
- Riesgo: si algún nodo no escribe su hash, `ledger_mismatch_detected` puede quedar en falso por ausencia de datos.
- Propuesta: añadir flag de completitud (`ledger_hashes_complete`) para distinguir “match real” de “falta de dato”.

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] Hashes visibles en debug trace.
- [ ] Hashes visibles en evento LiveTrace2.
- [ ] Mismatch no bloquea ejecución.

Reproducción:
```bash
pytest -q backend/tests/test_semantic_runtime_v1.py -k trace_exposes_ledger_hash_observability
rg -n "ledger_mismatch_detected" backend/negotiation
```
