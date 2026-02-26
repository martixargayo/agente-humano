# V01 — P0 ledger sync: effective semantic ledger

## A) Qué se afirma que cambió
- Se introdujo una utilidad central para reconciliar ledger persistido + ledger del judge del turno.
- Se define `effective_semantic_ledger` una sola vez en planner node.
- Planner consume ese ledger efectivo al renderizar prompt.
- Executor consume la misma fuente efectiva, evitando drift planner/executor.

## B) Dónde está en el repo (rutas + símbolos)
- `backend/negotiation/semantic_ledger_utils.py`
  - `normalize_semantic_ledger`
  - `build_effective_semantic_ledger`
  - `semantic_ledger_hash`
- `backend/negotiation/nodes/planner_node.py`
  - `state["effective_semantic_ledger"]`
- `backend/negotiation/phase_policy_planner.py`
  - parámetro `effective_semantic_ledger`
- `backend/negotiation/executor/render_executor.py`
  - lectura de `state.get("effective_semantic_ledger")`

## C) Evidencia 1 — Diff / Snippets (con contexto)
### C1. Reconciliación efectiva
```python
# backend/negotiation/semantic_ledger_utils.py

def build_effective_semantic_ledger(progress_state: dict | None, semantic_judge: dict | None) -> dict:
    persisted = normalize_semantic_ledger(
        ((progress_state or {}).get("semantic_ledger") if isinstance(progress_state, dict) else {}),
        None,
    )
    judge_ledger = normalize_semantic_ledger(
        ((semantic_judge or {}).get("semantic_ledger") if isinstance(semantic_judge, dict) else {}),
        persisted,
    )
    return normalize_semantic_ledger(judge_ledger, persisted)
```
Explicación: base persistida + overlay suave de judge con fallback.

### C2. Cálculo único por turno
```python
# backend/negotiation/nodes/planner_node.py

effective_ledger = build_effective_semantic_ledger(
    progress_state,
    state.get("semantic_judge") if isinstance(state.get("semantic_judge"), dict) else {},
)
state["effective_semantic_ledger"] = effective_ledger
state["effective_ledger_hash"] = semantic_ledger_hash(effective_ledger)
```
Explicación: se fija en state antes del planner llm call.

### C3. Planner + executor leen misma fuente
```python
# backend/negotiation/phase_policy_planner.py
semantic_ledger = (
    effective_semantic_ledger
    if isinstance(effective_semantic_ledger, dict)
    else build_effective_semantic_ledger(...)
)

# backend/negotiation/executor/render_executor.py
semantic_ledger = state.get("effective_semantic_ledger") if isinstance(state.get("effective_semantic_ledger"), dict) else ...
```

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "build_effective_semantic_ledger|effective_semantic_ledger" backend/negotiation
```
Debe mostrar referencias en util, planner_node, planner core y executor renderer.

## E) Evidencia 3 — Runtime / Prompt rendering
- Test existente valida presencia del mismo contenido (`"inicio"`) en planner y executor prompt:
  - `test_effective_ledger_is_shared_by_planner_and_executor`.
- En ese test ambos prompts contienen `SEMANTIC_LEDGER_JSON` y mismo valor semántico.

## F) Evidencia 4 — Telemetría / LiveTrace2
- Se calcula hash del ledger efectivo y se expone en state (V02 detalla payload completo).

## G) Qué podría estar mal / riesgos detectados
- Riesgo: si judge degrada y trae ledger pobre, la consistencia será alta pero la calidad baja.
- Riesgo: fallback dual en planner core puede ocultar errores de wiring si no se observa hash mismatch.
- Propuesta (no aplicar aquí): añadir contador de “effective ledger built by fallback path” como métrica.

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] `effective_semantic_ledger` existe y se fija en planner node.
- [ ] Planner renderiza `SEMANTIC_LEDGER_JSON` desde effective ledger.
- [ ] Executor renderiza `SEMANTIC_LEDGER_JSON` desde la misma fuente.
- [ ] Test `test_effective_ledger_is_shared_by_planner_and_executor` pasa.

Reproducción:
```bash
pytest -q backend/tests/test_semantic_runtime_v1.py -k effective_ledger_is_shared
rg -n "effective_semantic_ledger" backend/negotiation
```
