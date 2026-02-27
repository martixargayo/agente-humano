# Diagnóstico: por qué `memory_long_compact` sigue en `SIN_RESUMEN_AUN`

## Hallazgo principal
`_refresh_dual_memory(...)` sí llega a generar `memory_long`, pero ese valor se pierde inmediatamente al final del turno porque `run_negotiation_agent(...)` sobreescribe `state.progress_state` con `new_graph_state["progress_state"]` (sin los campos de memoria recién calculados).

## Evidencia resumida
- `run_negotiation_agent` construye `graph_state.long_memory` desde `state.progress_state.memory_long` al inicio del turno.
- El executor renderiza `memory_long_compact` usando `state["long_memory"]`.
- `_refresh_dual_memory` se ejecuta **después** del executor y sí marca `summarizer_called=True` cuando hay overflow.
- Luego `run_negotiation_agent` reasigna `state.progress_state = new_graph_state["progress_state"]`, borrando los campos `memory_long`, `memory_short`, `memory_long_turns_summarized` añadidos por `_refresh_dual_memory`.

## Reproducción local (simulada)
Con `NEGOTIATION_MEMORY_SHORT_TURNS=4` y 6 mensajes de usuario secuenciales:
- turnos 5 y 6: `refresh_meta.summarizer_called=True`, `memory_long_updated=True`.
- pero `state.progress_state.memory_long` queda `None` tras cada turno.

Esto confirma: el resumen se calcula, pero no persiste al estado utilizado para el próximo render del executor.
