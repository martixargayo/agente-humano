# LiveTrace2 semantic mapping fix (world_judge input + executor final output)

## Repro y diagnóstico

### 1) Backend + turnos

Comandos ejecutados:

1. `uvicorn app:app --host 0.0.0.0 --port 8000`
2. `curl -X POST http://127.0.0.1:8000/negociar ...` (2 turnos)

Resultado en este entorno:

- `/negociar` devolvió 500 por falta de `OPENAI_API_KEY`.
- Aun así se validó stream SSE y mapeo con tests + snapshots del adapter.

### 2) Stream

Comando ejecutado:

- `curl -N http://127.0.0.1:8000/livetrace2/stream | head -n 80`

Salida observada (en ventana corta):

- `: connected`

No se observaron `event: trace2` en esa ventana porque no se pudieron generar turnos reales por el 500 del endpoint `/negociar` en este entorno.


### Copia de `trace2 event`

Debido al 500 en `/negociar` (falta `OPENAI_API_KEY`), el stream en esta sesión sólo emitió `: connected` durante la captura corta.

Para dejar evidencia del shape real post-fix del adapter, se extrajo un `event: trace2` desde `_livetrace2_sse_generator` (mismo serializador del stream) y se guardó en:

- `docs/diagnostics/livetrace2_trace2_event_after_mapping_fix.json`

## Source of truth y rutas de campos

Búsquedas ejecutadas:

- `rg -n "build_livetrace2_event|append_livetrace2_event|debug_trace|trace_runtime|planner_meta|world_judge_meta|executor_output" backend -S`
- `rg -n "judge_input_prompt_rendered|judge_output_text_rendered|planner_input_prompt_rendered|planner_output_text_rendered" backend -S`
- `rg -n "render_meta|word_cap_limit|_enforce_executor_v2_contract" backend -S`

### A) Prompt renderizado del judge

- Se produce en `world_judge_llm(...)` como:
  - `judge_input_prompt_rendered`
  - `judge_output_text_rendered`
- Se guarda dentro de `state["world_debug"]["world_judge_meta"]` en `world_updater_node`.
- Se persiste al trace por turno en `run_negotiation_agent` como `debug_trace[].world_judge_meta`.

### B) Output final vs raw del executor

- Raw LLM (texto bruto) se conserva en telemetría (`trace_runtime.llm_calls[].output_text_rendered`).
- Output final (normalizado + enforce) queda en:
  - `state["executor_output"]`
  - `state["assistant_message"]`
- `run_negotiation_agent` persiste `debug_trace[].executor_output`.

## Problema detectado (antes)

1. `world_judge_llm` aparecía con **Entrada = NOT_CAPTURED** porque el adapter no leía `world_judge_meta.judge_input_prompt_rendered`.
2. `executor_llm` mostraba la **Salida raw** del LLM en vez del output final usado por backend (`state.executor_output`).

## Fix mínimo aplicado

### 1) world_judge_llm input

En el adapter semántico (`build_semantic_turn_model`):

- Se añade lectura preferente de `world_judge_meta.judge_input_prompt_rendered`.
- Si existe, se setea:
  - `input_prompt_rendered`
  - `input_capture_state="captured"`

Para salida del judge:

- Se agrupa en `output_payload_parsed`:
  - `llm_raw_output_text` (de `judge_output_text_rendered`)
  - `semantic_judge_final` (normalizado)

Sin inventar datos: sólo se usan fuentes ya presentes en `world_judge_meta` y `semantic_judge`.

### 2) executor_llm output final

En el adapter:

- Se fuerza que `executor_llm` muestre como principal `output_payload_parsed.final_executor_output = state.executor_output`.
- Se conserva raw para debug en:
  - `output_payload_parsed.llm_raw_output_text`
  - `output_payload_parsed.llm_raw_output_payload`

Así la UI enseña el output final real, y el raw queda disponible sin perder trazabilidad.

## Contrato adicional (asked_question + slots)

Se confirmó y mantiene `_enforce_executor_v2_contract`.
Además, el output final garantiza:

- si `asked_question == true` y `requested_info_slots == []` -> `requested_info_slots=["clarify_context"]`.

## Antes/Después

- Antes: snapshot previo de evento renderizable: `docs/diagnostics/livetrace2_first_trace2_event.json`.
- Después: snapshot con mapeo corregido: `docs/diagnostics/livetrace2_trace2_event_after_mapping_fix.json`.

En el “después”:

- `world_judge_llm.input_prompt_rendered` ya está presente cuando existe meta.
- `executor_llm.output_payload_parsed.final_executor_output` coincide con el output final del estado.

## Verificaciones ejecutadas

1. `python -m py_compile backend/negotiation/telemetry/live_trace2.py backend/tests/test_livetrace2_stream.py`
2. `pytest -q backend/tests/test_livetrace2_stream.py backend/tests/test_semantic_runtime_v1.py`
3. `curl -N http://127.0.0.1:8000/livetrace2/stream | head -n 80`

## Nota sobre captura visual del panel

Se intentó captura con Playwright del panel `/livetrace2`, pero el entorno del navegador no permitió completar la ejecución de forma estable en esta sesión.
Se dejó evidencia funcional en tests y snapshots JSON de evento antes/después.
