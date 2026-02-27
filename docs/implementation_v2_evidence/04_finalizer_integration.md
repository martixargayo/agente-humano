# 04 — Integración de `EXECUTOR_FINALIZER_V1`

## Claim
El pipeline actual incluye finalizer post-executor, con feature flags (`enabled` + `mode`), una sola llamada LLM (sin retries) y validación/normalización determinista antes y después.

## Evidence
- Integración en pipeline de `executor_node`:
  - Draft executor normalizado: `normalize_executor_output(executor_output)` en líneas 125–126 de `backend/negotiation/nodes/executor_node.py`.
  - Parseo de `objective_delta/tactic` desde planner hint antes de finalizer en líneas 128–130.
  - Activación condicional por flag `_finalizer_enabled()` en línea 140.
  - Llamada única LLM (`llm.invoke([...])`) en líneas 173–177.
  - No bucle/retry en finalizer: `retry_count=0` al registrar llamada en línea 200.
  - Validación determinista post-finalizer con `normalize_executor_output(parsed)` en línea 181 y nueva normalización final en línea 214.
- Feature flags y modo:
  - `_finalizer_enabled()` usa `NEGOTIATION_EXECUTOR_FINALIZER_ENABLED` en líneas 60–62.
  - `_finalizer_mode()` usa `NEGOTIATION_EXECUTOR_FINALIZER_MODE` (`active|shadow`) en líneas 64–67.
  - En modo `active`, reemplaza salida draft por `final_candidate` en líneas 211–212.
- Cliente LLM del finalizer:
  - `get_executor_finalizer_llm()` en `backend/negotiation/llm_clients.py` líneas 57–66.
- Prompt finalizer runtime:
  - Import de constantes finalizer en `backend/negotiation/nodes/executor_node.py` líneas 22–25.
  - Construcción de user prompt finalizer con inputs requeridos en líneas 152–170.

## Reasoning
La ruta está cableada exactamente como post-procesador del executor, con control explícito de activación y modo. No hay retries de finalizer y la salida mantiene forma `executor_v2` por normalización determinista.

## How to reproduce
1. Ver ejecución del nodo:
   - `nl -ba backend/negotiation/nodes/executor_node.py | sed -n '120,230p'`
2. Ver flags:
   - `nl -ba backend/negotiation/nodes/executor_node.py | sed -n '56,72p'`
3. Ver cliente finalizer:
   - `nl -ba backend/negotiation/llm_clients.py | sed -n '50,70p'`
4. (Baseline histórico de esta línea de trabajo) ver commits recientes:
   - `git log --oneline -n 5`
