# 02 — `world_state` no avanza (`interaction:{}` y `turn_idx=0` recurrente)

## Síntoma observado
- En prompts se observa `WORLD_COMPLETO_JSON` repetidamente vacío (`interaction: {}` / sin señales útiles).
- `world_state_meta.turn_idx=0` aparece reiteradamente en vez de avanzar por turno.

## Evidencias de LiveTrace (campos/mismatch)
- `executor_llm.input_prompt_rendered` incluye bloque `I) WORLD_COMPLETO_JSON` con contenido mínimo/constante.
- En nodos intermedios, no hay evidencia de actualización incremental del estado mundial por turno.

## Hipótesis de causa raíz (root cause)
### Causa principal (alta probabilidad)
**El actual updater de world está stub y retorna default**:
- `update_world_state(...)` descarta inputs y siempre devuelve `default_world_state()`.
- `default_world_state()` no incluye `world_state_meta.turn_idx`.
- `world_updater_node` actualmente ejecuta judge semántico, pero **no llama** a `update_world_state` ni persiste diffs de mundo.

Resultado: `world_state` permanece plano/vacío y sin metadatos de avance.

### Causa secundaria
- Existen utilidades que esperan `world_state_meta.turn_idx` (ej. compat/migrations), pero el estado runtime de este flujo no lo escribe, quedando en cero por default/fallback de lectura.

## Pistas concretas en código
- `update_world_state` devuelve siempre default.
- `world_updater_node` sólo setea `semantic_judge` y `world_debug`, no muta `state["world_state"]`.
- El prompt de executor consume `world_state` tal cual (sin enriquecer).

### Snippets relevantes
```python
# backend/negotiation/world_state_updater.py
def update_world_state(prev_world: dict, user_message: str, **kwargs) -> tuple[dict, dict]:
    del prev_world, user_message, kwargs
    return default_world_state(), {"extractor_used": False}
```

```python
# backend/negotiation/nodes/world_node.py
state["semantic_judge"] = judgement
state["world_debug"] = {
    "semantic_judge": judgement,
    "world_judge_meta": judge_meta,
}
return state
```

```python
# backend/negotiation/executor/render_executor.py
prompt = EXECUTOR_USER_PROMPT.format(
    ...
    world_json=json.dumps(world_state, ensure_ascii=False),
)
```

## Pruebas/validaciones para demostrarlo
1. **Unit test world monotonicity**:
   - Dado `turn_count` incremental, verificar que `world_state_meta.turn_idx` también incrementa.
   - Actualmente debería fallar (o quedar ausente/0).
2. **Trace assertion**:
   - Durante N turnos, assert que hash de `world_state` no sea idéntico siempre.
3. **Debug hooks LiveTrace2**:
   - Exponer en payload un resumen: `world_state_meta.turn_idx`, `world_state_changed_keys` por turno.

## Parche sugerido (propuesta, no implementado)
- Implementar actualización real de `world_state` por turno:
  - Llamar `update_world_state` desde `world_updater_node`.
  - Persistir `world_state_meta.turn_idx = turn_count`.
  - Mantener `prev_world_state` y `world_diff` con cambio real.
- Si el extractor no está listo, al menos aplicar patch mínimo:
  - Copiar estado previo + actualizar `world_state_meta.turn_idx` y timestamp.

## Riesgos y casos borde
- Si el world extractor mete ruido, planner podría sobreajustar fase por datos espurios.
- Asegurar compatibilidad con migración v3 (`world_buckets` / `world_state_meta`) para no romper sesiones antiguas.
