# LiveTrace2 semantic adapter (contrato UI vs payload semántico)

## 0) Repro obligatoria

Comandos ejecutados:

1. `curl -N http://127.0.0.1:8000/livetrace2/stream | head -n 80`
   - Resultado observado en este entorno: handshake SSE (`: connected`) sin `event: trace2` adicional durante la ventana corta de captura.

2. `curl -iN http://127.0.0.1:8000/livetrace2/stream` (timeout corto)
   - Resultado: `HTTP/1.1 200 OK`, `content-type: text/event-stream`, chunk inmediato `: connected`.

Nota: no fue posible generar turnos reales vía `/negociar` en este entorno por falta de `OPENAI_API_KEY`, por eso no apareció `event: trace2` en ese intervalo de captura.

## 1) Source of truth del contrato UI

Búsqueda ejecutada:

- `rg -n "EventSource\(|trace2|NO TIMESTAMPS|NOT_CAPTURED|visibles=|latencia|world_gate|planner_llm|executor_llm" backend -S`

Contrato esperado por la UI (`backend/app.py`, bloque HTML/JS de `/livetrace2`):

- Evento SSE: `trace2`, parseado con `JSON.parse(event.data)`.
- Campos top-level usados por cards:
  - `turn_idx`, `session_id`, `trace_index`, `started_at`, `ended_at`, `total_latency_ms`
  - `user_message`/`input_message`/`message` para “User”
  - `assistant_message`/`final_reply`/`output_text`/`reply` para “IA”
- `nodes[]` esperado para detalle/resumen por nodo.
- Cada nodo espera (al menos):
  - `node_name`, `node_type`, `status`, `latency_ms`, `started_at`, `ended_at`
  - opcionales de captura: `input_prompt_rendered`, `output_text_rendered`, `input_payload_raw`, `output_payload_raw`
- Strings de fallback visibles: `NO TIMESTAMPS`, `NOT_CAPTURED`, `missing`, `visibles=`, `latencia=`.

## 2) Tabla “UI field → source actual”

| UI field | Source real usado | Fallback aplicado |
|---|---|---|
| User | `trace_item.user_message` | `input_message`, `message`, `payload.user_message`, `"—"` |
| IA | `trace_item.assistant_message` o `executor_output.response_text` | `final_reply`, `output_text`, `reply`, `"—"` |
| world_judge_llm latency | `trace_runtime.llm_calls[name=world_judge_llm].latency_ms` | `world_judge_meta.judge_latency_ms`, luego `0` |
| planner_llm latency | `trace_runtime.llm_calls[name=planner_llm].latency_ms` | `planner_meta.planner_latency_ms`, luego `0` |
| executor_llm latency | `trace_runtime.llm_calls[name=executor_llm].latency_ms` | `0` |
| timestamps nodo | `trace_runtime.*.start_ts/end_ts` | `world_judge_meta.judge_start_ts/judge_end_ts`, `planner_meta.planner_start_ts/planner_end_ts`, luego vacío |
| timestamps turno | min/max de timestamps de nodos | `event.ts` |
| total latencia turno | suma de `nodes[].latency_ms` | `0` |

## 3) Fix aplicado (adapter adaptativo)

Se eligió **Opción B** (mínimo robusto backend): adaptar `build_livetrace2_event(...)` para emitir shape renderizable por la UI.

### 3.1 Compat legacy

Si `trace_item` ya trae `nodes` (timeline legacy), se preserva sin romper compatibilidad.

### 3.2 Payload semántico v1 (sin timeline)

Se construye turn model renderizable con:

- `user_message`
- `assistant_message`
- `nodes[]` con al menos:
  - `world_judge_llm`
  - `planner_llm`
  - `executor_llm`
- `started_at`, `ended_at`, `total_latency_ms`
- `payload` crudo para inspección

Además se enriqueció `state.debug_trace` en `run_negotiation_agent` para incluir:

- `user_message`, `assistant_message`
- `planner_meta`, `world_judge_meta`, `trace_runtime`

Eso permite que el adapter tome latencias/timestamps reales cuando están disponibles.

## 4) JSON antes/después

### Antes (shape no compatible con UI)

```json
{
  "payload": {
    "semantic_judge": {"schema_version": "judge_semantic_v1"},
    "planner_semantic_output": {"schema_version": "planner_semantic_v1"},
    "executor_output": {"response_text": "..."},
    "progress_state": {}
  }
}
```

### Después (shape renderizable)

Ver snapshot generado: `docs/diagnostics/livetrace2_first_trace2_event.json`.

Incluye `user_message`, `assistant_message` y nodos `world_judge_llm/planner_llm/executor_llm` en estado `ok`.

## 5) Bonus contrato executor_v2

Se verificó que `_enforce_executor_v2_contract` se ejecuta al final de `render_executor_output`.

Ajuste mínimo aplicado:

- Si `asked_question=true` y `requested_info_slots=[]`, se fuerza `requested_info_slots=["clarify_context"]`.

Sin cambiar diseño del runtime semántico; solo se endurece consistencia de contrato de salida.
