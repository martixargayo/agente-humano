# Diagnóstico: campos vacíos en runtime semántico (LiveTrace2 / prompts reales)

## 0) Reproducción + evidencia obligatoria

### Método usado (smoke existente sin depender de red)
Se ejecutó un turno semántico real del pipeline (`run_negotiation_agent`) con dummies de LLM para evitar dependencia externa, y se serializó:
- `trace_item` del turno
- evento `trace2` generado por `build_livetrace2_event`

Archivo de evidencia:
- `docs/diagnostics/context_fields_empty_repro_trace2.json`

### Evidencia de payload trace2 con campos vacíos
En el `trace2_event.payload.trace_runtime.llm_calls` se ve:
- Planner prompt con:
  - `OBJECTIVE_SUMMARY:` vacío
  - `FULL_PROFILES_BLOCK:` vacío
  - `MEMORY_SHORT:` vacío
  - `MEMORY_LONG:` vacío
- Executor prompt con:
  - `L) PHASE_MAP_JSON (opcional)` = `{}`
  - `A) BLOQUE_PERFILES_COMPLETOS` con `persona:{}, scene:{}`

### Snippet exacto (planner) donde se ve vacío
```text
OBJECTIVE_SUMMARY: 
FULL_PROFILES_BLOCK: 
MEMORY_SHORT: 
MEMORY_LONG: 
SEMANTIC_LEDGER_JSON: {"lo_que_ya_se_toco": [], "lo_que_ya_pregunte": [], "lo_que_falta_pero_no_insistire": []}
PHASE_MAP_JSON: {"clima_humano": ...}
```

### Snippet exacto (executor) donde se ve vacío
```text
A) BLOQUE_PERFILES_COMPLETOS
{"persona": {}, "scene": {}, "style": {"max_words": 30, "max_questions": 1}}
...
L) PHASE_MAP_JSON (opcional)
{}
```

---

## 1) Source of truth por campo

## 1.1 OBJECTIVE_SUMMARY

### Dónde se “debería” construir
- Existe helper: `build_objective_summary(objective, scene_profile, persona_profile)` en `backend/negotiation/llm_planning_context.py`.

### Dónde se inyecta al prompt
- Planner user prompt template: `OBJECTIVE_SUMMARY: {objective_summary}` en `backend/prompts.py`.
- Render efectivo: `objective_summary = str(objective or "")[:500]` en `backend/negotiation/phase_policy_planner.py`.

### Dónde se setea `state["objective"]`
- En `run_negotiation_agent`: `"objective": state.negotiation_objective or ""`.
- Nodos planner/executor fuerzan vacío si falta (`_ensure_objective -> ""`).

### Llamada actual en planner semántico
- `phase_policy_planner_node` llama `deps.plan_phase_policy(... objective=state.get("objective", "") ...)`.
- **No** llama `build_objective_summary(...)`; sólo pasa string plano de objective.

**Conclusión puntual:** el sitio de inyección existe, pero la construcción rica está desconectada y el default efectivo actual es cadena vacía.

---

## 1.2 FULL_PROFILES_BLOCK

### Dónde se “debería” construir
- Builder completo disponible:
  - `build_full_roleplay_profiles(...)`
  - `build_planner_context_block_full(...)`
  - `build_executor_context_block_full(...)`
  en `backend/negotiation/llm_planning_context.py`.

### Dónde se inyecta al prompt
- Planner template: `FULL_PROFILES_BLOCK: {full_profiles_block}` (`backend/prompts.py`).
- Planner render actual: `full_profiles_block=""` (`backend/negotiation/phase_policy_planner.py`).
- Executor render actual: `full_profiles_block=json.dumps({"persona": persona, "scene": scene, "style": style})` (`backend/negotiation/executor/render_executor.py`).

### Estado de render_state/persona_id/scene_id/style_id
- `default_progress_state()` sí incluye `render_state` con defaults (`persona_id/scene_id/style_id = "default"`) en `backend/negotiation/schemas.py`.
- Pero el resolver de perfiles actual está stub:
  - `resolve_render_profiles(render_state): return {}, {}, {"max_words": 30, "max_questions": 1}` en `backend/negotiation/elementos/render/__init__.py`.

### ¿Builders devuelven vacío por defaults?
- Los builders de `llm_planning_context.py` pueden devolver bloque no vacío.
- Sin embargo, en runtime actual **no se llaman** en planner/executor.
- Además, el resolver central de perfiles devuelve `{}` para persona/scene.

**Conclusión puntual:** hay mezcla de “desconectado” + “stub activo”. El path runtime que se usa hoy deja perfiles vacíos por diseño actual.

---

## 1.3 MEMORY_SHORT / MEMORY_LONG

### Dónde se “debería” construir
- Pipeline de memoria aún existe en `backend/negotiation/context_utils.py`:
  - `build_memory_context(...)`
  - `maybe_refresh_summary(...)`
- Job manager de resumen existe en `backend/negotiation/summary_jobs.py`.

### Persistencia en progress_state/session
- Memoria larga vive en `SessionState.summary` (`backend/state.py`).
- En runtime negociación, `run_negotiation_agent` setea:
  - `short_memory=""`
  - `long_memory=state.summary or ""`

### ¿API lo pasa o lo deja vacío?
- `/negociar` solo llama `run_negotiation_agent`; no dispara refresh de summary.
- El enqueue de summary diferido está en `/tts` (no en `/negociar`) en `backend/app.py`.

### Resultado actual
- `MEMORY_SHORT` siempre vacío (hardcode).
- `MEMORY_LONG` suele vacío hasta que exista `state.summary` (y el pipeline de resumen se ejecute por otra vía).

**Conclusión puntual:** el sistema de memoria existe, pero está desconectado del flujo de negociación en el punto donde se necesitan estos campos.

---

## 1.4 PHASE_MAP_JSON en executor (sale `{}`)

### Dónde existe phase map
- `PHASE_MAP_V1` definido en `backend/negotiation/phase_policy_planner.py`.
- Planner lo inyecta correctamente en su propio prompt (`phase_map_json=json.dumps(PHASE_MAP_V1, ...)`).

### Por qué no llega al executor
- Executor lee `state.get("phase_map_json", {})` en `backend/negotiation/executor/render_executor.py`.
- No hay escritura previa de `state["phase_map_json"]` en planner node ni en graph state.

**Conclusión puntual:** mismatch de wiring de estado: planner usa `PHASE_MAP_V1` local; executor espera key de estado nunca poblada.

---

## 2) Causa exacta por campo (A/B)

| Campo | Estado actual | Causa raíz | A/B |
|---|---|---|---|
| `OBJECTIVE_SUMMARY` | Vacío cuando `state.negotiation_objective` no existe | builder rico existe pero no se usa; objective default = `""` sin fallback semántico | **A (mal cableado)** |
| `FULL_PROFILES_BLOCK` (planner) | Siempre `""` | hardcode explícito en planner | **B (stub/eliminado en runtime actual)** |
| `FULL_PROFILES_BLOCK` (executor) | persona/scene vacíos | resolver de perfiles stub retorna `{}` y además no se usa builder completo | **B + A** |
| `MEMORY_SHORT` | Siempre vacío | hardcode en graph state y no se llama `build_memory_context` | **A (desconectado)** |
| `MEMORY_LONG` | Vacío frecuentemente | depende de `state.summary`; pipeline existe pero no se integra a `/negociar` en tiempo útil | **A (desconectado)** |
| `PHASE_MAP_JSON` (executor) | `{}` | executor lee key inexistente (`state["phase_map_json"]`) | **A (key/wiring mismatch)** |

### Referencia por archivo/función (value actual vs esperado)
- `backend/negotiation/phase_policy_planner.py::plan_phase_policy`
  - actual: `objective_summary = str(objective or "")`, `full_profiles_block=""`
  - esperado: objective con fallback no vacío + bloque perfiles completo.
- `backend/negotiation/executor/render_executor.py::render_executor_output`
  - actual: `phase_map_json=json.dumps(state.get("phase_map_json", {}))`
  - esperado: mapa de fases real (mismo del planner o versión compacta).
- `backend/negotiation/negotiation_graph.py::run_negotiation_agent`
  - actual: `short_memory=""`, `long_memory=state.summary or ""`
  - esperado: memoria corta/larga construidas explícitamente (o sentinel intencional).
- `backend/negotiation/elementos/render/__init__.py::resolve_render_profiles`
  - actual: retorna `{},{},style_minimo`
  - esperado: persona/scene/style válidos según `render_state`.

---

## 3) Target mínimo visible en LiveTrace2 cuando esté bien

- `OBJECTIVE_SUMMARY`: string no vacío (aunque sea default explícito y trazable).
- `FULL_PROFILES_BLOCK`: persona/scene/style presentes (si no hay configuración, defaults explícitos, no `{}`).
- `MEMORY_SHORT`: 1–2 líneas o sentinel explícito (`"SIN_MEMORIA_CORTA_INTENCIONAL"`) con razón documentada.
- `MEMORY_LONG`: resumen válido o sentinel explícito documentado.
- `PHASE_MAP_JSON` (executor): mismo mapa usado por planner (o compacto), nunca `{}` silencioso.

---


## 3.1 Perfil objetivo explícito (comentario de revisión incorporado)

El target de `FULL_PROFILES_BLOCK` y defaults de runtime debe ser exactamente el preset **Carlos buyer Mustang67** ya presente en código (`CARLOS_PERSONA_PROFILE`, `CARLOS_SCENE_PROFILE`, `CARLOS_STYLE_CONTRACT`, `CARLOS_CONSTRAINTS_STRUCT`).

- `persona_id`: `buyer_mustang67_v1`
- `scene_id`: `mustang67_in_person_viewing`
- `style_id`: `psyplay_compact`
- constraints anti-drift: `forbid_claims/forbid_formats/forbid_behaviors/dialogue_dynamics/end_rule/max_questions`

Esto confirma que no hay que inventar nuevos objetos: el contenido ya existe y el problema es de **wiring** para que llegue a planner/executor. 

---
## 4) Evidencia de búsquedas (`rg`) pedidas

Se ejecutaron estas búsquedas para localizar construcción e inyección:

- `rg -n "OBJECTIVE_SUMMARY|objective_summary|build_objective_summary|\bobjective\b" ...`
- `rg -n "FULL_PROFILES_BLOCK|full_profiles_block|build_full_roleplay_profiles|build_planner_context_block_full|build_executor_context_block_full|resolve_render_profiles|render_state|persona_id|scene_id|style_id" ...`
- `rg -n "memory_short|memory_long|short_memory|long_memory|summary_text|summary_jobs|deferred_summary|summary|build_memory_context" ...`
- `rg -n "phase_map_json|PHASE_MAP|PHASE_MAP_V1|PHASE_MAP_V" ...`

(Los resultados completos se usaron para este diagnóstico y apuntan a los callsites listados arriba).

---

## 5) Veredicto de este paso

**Recomendación clara:** **Se arregla con wiring (mínimo)**.

No hace falta reintroducir motores legacy; hay piezas suficientes en código actual para poblar estos campos con cambios acotados de cableado/defaults explícitos.
