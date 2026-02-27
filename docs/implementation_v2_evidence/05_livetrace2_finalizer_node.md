# 05 — Evidencia LiveTrace2: nodo `executor_finalizer_llm`

## Claim
LiveTrace2 incluye un nodo adicional `executor_finalizer_llm` al final del flujo LLM y expone metadatos clave del finalizer.

## Evidence
- Constructor específico del nodo finalizer:
  - `_build_executor_finalizer_node(...)` en `backend/negotiation/telemetry/live_trace2.py` líneas 138–165.
- El nodo se agrega después del executor:
  - `executor_node = _build_executor_node(...)` y append en líneas 216–218.
  - `executor_finalizer_node = _build_executor_finalizer_node(...)` y append en líneas 220–222.
- Campos expuestos para debug:
  - `finalizer_called` en línea 159.
  - `finalizer_changed_from_draft` en línea 160.
  - `finalizer_fixes` en línea 161.
  - `latency_ms_finalizer` en línea 162.
- Telemetría runtime incluye el nodo lógico `executor_finalizer`:
  - `NODE_NAMES` incorpora `"executor_finalizer"` en `backend/negotiation/telemetry/trace_runtime.py` línea 16.

## Reasoning
El builder de LiveTrace2 ya sabe materializar y anexar el nodo finalizer, incluso con fallback usando `render_meta` cuando no hay `llm_call` crudo. La presencia de `executor_finalizer` en `NODE_NAMES` garantiza trazabilidad también en `trace_runtime`.

## How to reproduce
1. Inspección de LiveTrace2:
   - `nl -ba backend/negotiation/telemetry/live_trace2.py | sed -n '120,230p'`
2. Inspección de runtime nodes:
   - `nl -ba backend/negotiation/telemetry/trace_runtime.py | sed -n '1,30p'`
3. Ejecutar test específico:
   - `PYTHONPATH=backend pytest -q backend/tests/test_livetrace2_stream.py -k finalizer`
