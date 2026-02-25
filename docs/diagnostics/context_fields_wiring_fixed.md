# context_fields_wiring_fixed

## Resumen
Se implementó el wiring completo en runtime semántico v1 para que no vuelvan a salir vacíos:

- `OBJECTIVE_SUMMARY` (planner)
- `FULL_PROFILES_BLOCK` (planner)
- `MEMORY_SHORT` / `MEMORY_LONG` (planner y executor)
- `PHASE_MAP_JSON` (planner y executor) usando **source of truth único** nuevo.

## Before / After (snippets reales)

### Before (vacíos)
Fuente: `docs/diagnostics/context_fields_empty_repro_trace2.json`.

Planner prompt:
- `OBJECTIVE_SUMMARY:` vacío
- `FULL_PROFILES_BLOCK:` vacío
- `MEMORY_SHORT:` vacío
- `MEMORY_LONG:` vacío

Executor prompt:
- `A) BLOQUE_PERFILES_COMPLETOS` con `persona: {}` / `scene: {}`
- `L) PHASE_MAP_JSON (opcional)` con `{}`

### After (poblados)
Fuente: `docs/diagnostics/context_fields_wiring_fixed_trace2.json`.

Planner prompt ahora muestra:
- `OBJECTIVE_SUMMARY: Objetivo: avanzar...` (o derivado por builder/default)
- `FULL_PROFILES_BLOCK: BLOQUE_PERFILES_COMPLETOS ... PERSONA/ESCENA/STYLE/CONSTRAINTS`
- `MEMORY_SHORT: ...` (o `SIN_MEMORIA_CORTA_AUN`)
- `MEMORY_LONG: ...` (o `SIN_RESUMEN_AUN`)
- `PHASE_MAP_JSON` con el mapa nuevo (incluye marker `"cordialidad real, sin estrategia."`)

Executor prompt ahora muestra:
- `A) BLOQUE_PERFILES_COMPLETOS` con `buyer_mustang67_v1` y `mustang67_in_person_viewing`
- `H) MEMORIA` con campos no vacíos/sentinel explícito
- `L) PHASE_MAP_JSON (opcional)` con el mapa nuevo (no `{}`)

## Dónde se construye e inyecta ahora

## 1) PHASE_MAP_JSON (single source of truth)
- Source of truth: `backend/negotiation/phase_map.py::get_phase_map_v1()`.
- Planner: `backend/negotiation/phase_policy_planner.py` inyecta `phase_map_json=json.dumps(get_phase_map_v1(), ...)`.
- Executor: `backend/negotiation/executor/render_executor.py` usa `state["phase_map_json"]` y fallback a `get_phase_map_v1()`.
- Wiring de estado: `backend/negotiation/nodes/planner_node.py` setea `state["phase_map_json"]`.

## 2) FULL_PROFILES_BLOCK / BLOQUE_PERFILES_COMPLETOS
- `resolve_render_profiles` dejó de ser stub y resuelve perfiles reales con fallback explícito a `CARLOS_*` cuando IDs faltan o están en `default`.
- Planner: `backend/negotiation/phase_policy_planner.py` usa `build_planner_context_block_full(progress_state)`.
- Executor: `backend/negotiation/nodes/executor_node.py` obtiene perfiles via `build_full_roleplay_profiles(...)` y los pasa a render.

## 3) OBJECTIVE_SUMMARY
- `backend/negotiation/phase_policy_planner.py` aplica fallback en cascada:
  1. `state objective`
  2. `build_objective_summary(...)`
  3. default explícito
- Se traza `planner_meta["objective_source"] = state|builder|default`.

## 4) MEMORY_SHORT / MEMORY_LONG
- `backend/negotiation/negotiation_graph.py` llama `build_memory_context(...)` y llena `short_memory/long_memory` antes de planner+executor.
- Sentinels explícitos cuando no hay contenido: `SIN_MEMORIA_CORTA_AUN` y `SIN_RESUMEN_AUN`.
- `/negociar` ahora encola summary job diferido (`deferred_summary_enabled`) al final del turno para alimentar `state.summary` en turnos siguientes sin bloquear respuesta.

## Comandos ejecutados

```bash
python -m py_compile backend/app.py backend/negotiation/phase_map.py backend/negotiation/phase_policy_planner.py backend/negotiation/nodes/planner_node.py backend/negotiation/nodes/executor_node.py backend/negotiation/executor/render_executor.py backend/negotiation/negotiation_graph.py backend/negotiation/elementos/render/__init__.py backend/negotiation/elementos/render/persona_profiles.py backend/negotiation/elementos/render/scene_profiles.py backend/negotiation/elementos/render/style_contracts.py backend/tests/test_semantic_runtime_v1.py backend/tests/test_livetrace2_stream.py
```

```bash
pytest -q backend/tests/test_semantic_runtime_v1.py backend/tests/test_livetrace2_stream.py
```

```bash
# smoke local con dummies para generar evidencia trace2 after-fix
python - <<'PY'
# (script ejecutado desde backend/, genera docs/diagnostics/context_fields_wiring_fixed_trace2.json)
PY
```
