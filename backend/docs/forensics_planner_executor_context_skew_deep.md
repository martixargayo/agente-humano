# Forense profundo (nuevo): degradación persistente en `interfaz_usuario` no reproducida en `optimizador`

## 1. Resumen ejecutivo

Se ejecutó una investigación forense nueva centrada en `phase/planner/executor`, bootstrap de primer turno y estado efectivo posterior a `memory`.

Conclusión causal confirmada:

1. En runtime actual, **no aparece asimetría estructural** entre superficies cuando el input efectivo está alineado.
2. El síntoma “`Propuesta:` / estilo rígido administrativo” se reproduce de forma causal cuando `planner_input.planner_state.current_turn_goal` arrastra un goal stale.
3. El punto causal exacto es `planner_input.planner_state.current_turn_goal`.
4. Se aplicó fix mínimo adicional de bajo riesgo: **sanear `current_turn_goal` en `build_planner_input` (forzar `None` en input del planner)** para impedir anclajes tácticos de turnos previos.

## 2. Qué ya estaba descartado

- Runtime/cerebro distinto entre superficies.
- Causa pre-memory original (continuidad residual) como explicación única de este síntoma nuevo.
- Diferencia sistemática en phase/planner/executor en baseline limpio.

## 3. Nueva hipótesis central

Aunque se había añadido reset de goal al cambiar fase, podía persistir un vector residual: `planner_state.current_turn_goal` almacenado en sesión y reutilizado como ancla en turnos posteriores (especialmente en sesiones largas/reusadas).

## 4. Metodología

- Lectura estática de `flow_config.py` y builders de nodos.
- Harness dinámico con captura de payload real (`freeze_prompt_artifacts`) y stubs deterministas (`_call_structured`).
- Normalización de ruido (`turn_id`, `timestamp_iso`).
- Escenarios A/B:
  - baseline limpio,
  - primer turno fresh,
  - transición de fase en sesiones compartidas,
  - skew inyectado de `current_turn_goal` solo en interfaz (runtime actual),
  - skew inyectado con emulación legacy (sin saneado en planner input).

## 5. Evidencia experimental

Artefacto: `backend/docs/forensics_planner_executor_context_skew_run.json`

### Escenario baseline limpio
- `first_divergence = null`.

### Escenario primer turno fresh
- `first_divergence = null`.

### Escenario transición de fase en sesión compartida
- `first_divergence = null`.

### Skew inyectado en interfaz (runtime actual)
- Aunque se inyecta `current_turn_goal` stale en el estado de interfaz, el planner no lo recibe (sanitizado).
- Resultado: `first_divergence = null`, respuestas convergentes.

### Skew inyectado con emulación legacy
- Primera divergencia exacta: `planner_state.current_turn_goal`.
- Cascada a executor (`planner_output.decision`) y aparición de respuesta rígida tipo `Propuesta:`.

## 6. Primer punto exacto de divergencia

`planner_input.planner_state.current_turn_goal` cuando se permite arrastre stale (legacy behavior).

## 7. Impacto causal en calidad

- Goal stale mantiene al planner en táctica previa aunque la fase actual haya cambiado (o aunque el contexto pida cierre).
- Executor verbaliza ese sesgo como salida más esquemática/administrativa (`Propuesta:`), en lugar de formalización natural.

## 8. Solución implementada

Archivo: `backend/negociacion/orchestration/flow_config.py`

Cambio exacto:
- En `build_planner_input`, se clona `planner_state` y se fuerza `planner_state_for_input.current_turn_goal = None`.
- El estado original se conserva para trazabilidad interna; solo se elimina el ancla en el input del planner.

Por qué este fix es correcto:
- Ataca el punto causal exacto (ancla stale en input del planner).
- Es mínimo, no toca modelos/prompts/contratos de salida.
- Mantiene paridad de superficies al neutralizar una fuente de skew de estado persistente.

## 9. Validación y riesgos

Validación:
- test forense nuevo confirma:
  - runtime actual bloquea skew inyectado,
  - emulación legacy reproduce divergencia causal,
  - baseline limpio mantiene paridad.
- test de wiring asegura que `build_planner_input` no forwardea `current_turn_goal` previo.

Riesgos:
- Bajo: se pierde únicamente ese ancla textual en el planner input (que en la práctica era fuente de contaminación).
- No se alteran phase cards, selected_memory, response limits ni threading.

## 10. Estado final

- Causa nueva confirmada y cerrada a nivel de pipeline: arrastre de `planner_state.current_turn_goal` como ancla en planner input.
- Fix aplicado, validado y congelado con regresión.
- Si reaparecen síntomas de primer turno “raro”, el siguiente cuello de botella a auditar será guardrails/postproceso con ejecución live (no stub) para detectar rewrites de estilo no visibles en harness determinista.
