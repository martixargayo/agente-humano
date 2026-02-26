# 01 — Desincronización de `semantic_ledger` entre planner y executor

## Síntoma observado
- En el turno reportado (Turno 12), `world_judge_llm` produce `semantic_ledger` poblado.
- En el mismo turno, el prompt de `planner_llm` muestra `SEMANTIC_LEDGER_JSON` vacío.
- En ese mismo turno, el prompt de `executor_llm` sí refleja ledger poblado.

## Evidencias de LiveTrace (campos/mismatch)
- Nodo `world_judge_llm`: `output_payload_parsed.semantic_judge_final.semantic_ledger` con datos.
- Nodo `planner_llm`: `input_prompt_rendered` con `SEMANTIC_LEDGER_JSON: { ... [] ... }`.
- Nodo `executor_llm`: `input_prompt_rendered` con `SEMANTIC_LEDGER_JSON` ya actualizado.
- El modelo de evento de LiveTrace2 preserva estos tres nodos por separado (`semantic_judge_final`, `planner_llm`, `executor_llm`), por lo que el mismatch puede observarse sin ambigüedad de parsing.

## Hipótesis de causa raíz (root cause)
### Causa principal (alta probabilidad)
**Orden de pipeline incorrecto para el uso de ledger en planner**:
1. `world_updater_node` escribe `state["semantic_judge"]`.
2. `phase_policy_planner_node` se ejecuta **antes** de `progress_updater_node`.
3. El planner lee ledger desde `progress_state.semantic_ledger` (estado previo).
4. `progress_updater_node` recién después hace merge `semantic_judge.semantic_ledger -> progress_state.semantic_ledger`.
5. `executor_node` se ejecuta al final y ya consume el `progress_state` actualizado.

Resultado: planner consume ledger viejo; executor consume ledger nuevo.

### Causa secundaria (diseño de fuentes)
- Planner ignora explícitamente `judge_result` (`del ... judge_result`) en `plan_phase_policy`, por lo que aunque el judge tenga ledger nuevo, planner no lo usa como fuente directa.

## Pistas concretas en código
- **Orden de ejecución**: `world -> belief -> planner -> progress -> executor`.
- Planner toma ledger de `progress_state` y renderiza `SEMANTIC_LEDGER_JSON` desde ahí.
- Progress updater hace el merge de `semantic_judge` al ledger persistente.
- Executor renderiza su `SEMANTIC_LEDGER_JSON` desde `progress_state`, pero ya tras merge.

### Snippets relevantes
```python
# backend/negotiation/negotiation_graph.py
state = world_updater_node(state)
state = belief_updater_node(state)
state = phase_policy_planner_node(state)
state = progress_updater_node(state)
state = executor_node(state)
```

```python
# backend/negotiation/phase_policy_planner.py
semantic_ledger = (progress_state or {}).get("semantic_ledger", {})
...
user_prompt = PLANNER_SEMANTIC_V1_USER_PROMPT.format(
    ...
    semantic_ledger_json=json.dumps(semantic_ledger or {}, ensure_ascii=False),
)
```

```python
# backend/negotiation/progress_updater.py
incoming = (semantic_judge or {}).get("semantic_ledger") if isinstance(semantic_judge, dict) else {}
...
progress["semantic_ledger"] = semantic_ledger
```

```python
# backend/negotiation/phase_policy_planner.py
del allowed_policy_ids, judge_result
```

## Pruebas/validaciones para demostrarlo
1. **Instrumentación de snapshot por nodo**:
   - Loggear en cada nodo: hash/json de `progress_state.semantic_ledger` y `semantic_judge.semantic_ledger`.
   - Assert diagnóstico: en un turno, si `semantic_judge` cambió y planner no lo ve, marcar warning explícito.
2. **Unit test de orden**:
   - Estado inicial con ledger vacío y `semantic_judge` poblado tras world.
   - Ejecutar pipeline actual y validar que `planner_input_prompt_rendered` contiene ledger viejo.
3. **A/B con reorder local** (solo test):
   - Mover `progress_updater_node` antes de planner y verificar que `planner_input_prompt_rendered` coincide con judge.

## Parche sugerido (propuesta, no implementado)
- Opción A (recomendada): cambiar orden a `world -> belief -> progress -> planner -> executor`.
- Opción B: mantener orden, pero planner debe usar fuente `state.semantic_judge.semantic_ledger` como overlay sobre `progress_state.semantic_ledger`.
- Opción C: fusionar una versión “effective_semantic_ledger_for_turn” antes del planner.

## Riesgos y casos borde
- Reordenar nodos puede afectar features que dependan de `policy_decision` al actualizar progreso.
- Overlay dual puede introducir conflictos si judge devuelve ledger parcial o degradado (fallback).
- Importante definir precedencia estable (judge actual > progress previo, con fallback por clave).
