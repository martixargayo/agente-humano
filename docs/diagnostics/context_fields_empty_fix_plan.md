# Plan de fix mínimo (sin legacy) para campos vacíos de contexto

## Principios
- No reintroducir `planner_v2`, `judge_v2`, `plan_ledger`, `counters`.
- Cambios mínimos de wiring/defaults explícitos.
- Nada “mágico”: cuando no haya dato real, usar sentinel/documentar intención.

---

## Fix mínimo propuesto por campo


## 0.5 Defaults canónicos a fijar (revisión)

Usar como defaults explícitos los perfiles ya definidos en `backend/negotiation/elementos/render/carlos_buyer_preset.py` (sin redefinirlos en otro sitio):

- `CARLOS_PERSONA_PROFILE` (`persona_id=buyer_mustang67_v1`)
- `CARLOS_SCENE_PROFILE` (`scene_id=mustang67_in_person_viewing`)
- `CARLOS_STYLE_CONTRACT` (`style_id=psyplay_compact`, `max_words=30`, `max_questions=1`)
- `CARLOS_CONSTRAINTS_STRUCT` (anti-drift + dinámica + `[END]`)

Objetivo del fix: que `FULL_PROFILES_BLOCK` renderice estos objetos (o defaults equivalentes explícitos) en planner y executor, y que nunca salga `{}` para persona/scene.

---

## 1) OBJECTIVE_SUMMARY

### Propuesta
1. En `planner_node` o `plan_phase_policy`, calcular `objective_summary` con fallback explícito:
   - prioridad 1: `state["objective"]` si viene no vacío
   - prioridad 2: `build_objective_summary(...)` usando perfiles efectivos
   - prioridad 3: default explícito constante (ej. `"Objetivo conversacional: avanzar con claridad en la negociación actual."`)
2. Dejar trazado en `planner_meta` cuál fallback se usó (`objective_source`).

### Archivos a tocar
- `backend/negotiation/nodes/planner_node.py`
- `backend/negotiation/phase_policy_planner.py`
- (si hace falta) `backend/negotiation/llm_planning_context.py`

---

## 2) FULL_PROFILES_BLOCK

### Propuesta
1. Planner: reemplazar `full_profiles_block=""` por `build_planner_context_block_full(progress_state)`.
2. Executor: resolver perfiles desde `progress_state.render_state` (sin stub vacío) y pasar bloque no vacío:
   - usar `build_full_roleplay_profiles(...)` o `build_executor_context_block_full(...)`.
   - si faltan ids o están en `default`, hacer fallback explícito a `CARLOS_*` (no `{}`).
3. Mantener defaults explícitos cuando falten IDs (persona/scene/style por defecto), nunca `{}` silencioso.

### Archivos a tocar
- `backend/negotiation/phase_policy_planner.py`
- `backend/negotiation/nodes/executor_node.py`
- `backend/negotiation/executor/render_executor.py`
- `backend/negotiation/elementos/render/__init__.py` (eliminar stub mínimo)
- `backend/negotiation/llm_background.py` (si requiere ajuste por resolver)

---

## 3) MEMORY_SHORT / MEMORY_LONG

### Propuesta
1. Construir memoria en `run_negotiation_agent` antes del pipeline:
   - `long_memory, short_memory, meta = build_memory_context(...)`
2. Escribir ambos en `graph_state` (en vez de hardcode de `short_memory=""`).
3. Si no hay memoria real:
   - dejar string explícito documentado (o vacío intencional con bandera meta).
4. Opcional mínimo recomendado:
   - enqueue summary job desde `/negociar` al final del turno (como ya se hace en `/tts`) para que `long_memory` no dependa de rutas laterales.

### Archivos a tocar
- `backend/negotiation/negotiation_graph.py`
- `backend/negotiation/context_utils.py` (solo si se necesita helper extra)
- `backend/app.py` (`/negociar`, opcional recomendado)
- `backend/negotiation/summary_jobs.py` (solo si requiere helper de integración)

---

## 4) PHASE_MAP_JSON (executor)

### Propuesta
1. Single source of truth para phase map:
   - exportar helper `get_phase_map_v1()` o constante compartida.
2. Escribir `state["phase_map_json"]` en planner node tras planificar (o al iniciar graph_state).
3. Executor seguirá leyendo esa key, pero ahora siempre poblada.
4. Añadir test de consistencia planner-vs-executor para evitar drift.

### Archivos a tocar
- `backend/negotiation/phase_policy_planner.py`
- `backend/negotiation/nodes/planner_node.py`
- `backend/negotiation/negotiation_graph.py` (si se inicializa ahí)
- `backend/negotiation/executor/render_executor.py`

---

## Orden recomendado de implementación (exacto)

1. **PHASE_MAP_JSON wiring** (más acotado, bajo riesgo).
2. **FULL_PROFILES_BLOCK wiring** (planner + executor) y quitar stub crítico.
3. **OBJECTIVE_SUMMARY fallback explícito** (fuente + trazabilidad meta).
4. **MEMORY wiring mínimo** (`build_memory_context` en `run_negotiation_agent`).
5. **(Opcional recomendado) enqueue summary en `/negociar`** para alimentar memoria larga de forma natural.

---

## Riesgos
- Cambios de prompt pueden alterar estilo/respuesta del modelo (riesgo controlable con snapshots de prompt).
- Quitar stub de perfiles puede revelar dependencias no cubiertas por tests actuales.
- Memoria larga (summary JSON) puede venir vacía/invalid si no hay job de resumen; por eso conviene sentinel/meta.

---

## Tests / smoke a correr

1. **Unit: planner prompt context**
   - Verificar que `OBJECTIVE_SUMMARY` nunca queda vacío.
   - Verificar que `FULL_PROFILES_BLOCK` planner no queda vacío.
2. **Unit: executor prompt context**
   - Verificar `FULL_PROFILES_BLOCK` con persona/scene/style no vacíos.
   - Verificar `PHASE_MAP_JSON` distinto de `{}`.
3. **Unit: memory wiring**
   - Verificar que `short_memory/long_memory` en `graph_state` vienen de `build_memory_context`.
4. **Smoke semantic turn + trace2**
   - Ejecutar un turno y confirmar en `trace_runtime.llm_calls[*].input_prompt_rendered` que los cuatro bloques aparecen poblados o con sentinel explícito.
5. **Regression**
   - Mantener tests existentes de semantic runtime (`backend/tests/test_semantic_runtime_v1.py`) y livetrace2.

---

## Cierre

Diagnóstico indica que **no hace falta recrear módulos completos**; el camino correcto es **wiring mínimo + defaults explícitos** sobre piezas existentes.
