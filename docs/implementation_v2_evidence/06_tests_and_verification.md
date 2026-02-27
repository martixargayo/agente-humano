# 06 — Tests y verificación reproducible

## Claim
El estado actual del repositorio valida: igualdad literal de prompts, contrato por marcadores y visibilidad del nodo finalizer en LiveTrace2.

## Evidence
- Test de igualdad literal runtime vs docs:
  - `backend/tests/test_prompt_literals_runtime_vs_docs.py` líneas 24–40.
  - Verifica 8 constantes runtime contra `docs/prompts_literal_v2/*`.
- Test de LiveTrace2 con nodo finalizer:
  - `backend/tests/test_livetrace2_stream.py` líneas 180–222.
  - Afirma existencia de `executor_finalizer_llm` y campos `finalizer_called`, `finalizer_changed_from_draft`, `finalizer_fixes`, `latency_ms_finalizer`.
- Tests de contrato por marcadores:
  - `backend/tests/test_prompt_swap_wiring.py` líneas 275–286 (etiquetas `OBJECTIVE_DELTA` y `TACTIC` en hint normalizado).
  - `backend/tests/test_semantic_runtime_v1.py` líneas 437–438 (presencia de marcadores en normalización).

## Reasoning
Los tests cubren directamente los tres ejes críticos: source-of-truth literal de prompts, contrato técnico de `next_move_hint` y trazabilidad del finalizer en LiveTrace2.

## How to reproduce
- Suite focal ejecutada en esta validación:
  - `PYTHONPATH=backend pytest -q backend/tests/test_prompt_literals_runtime_vs_docs.py backend/tests/test_prompt_swap_wiring.py backend/tests/test_semantic_runtime_v1.py backend/tests/test_livetrace2_stream.py`
- Resultado observado:
  - `................................ssss...... [100%]`
  - Warnings de deprecación/FutureWarning sin fallos de asserts.
- Chequeos de higiene runtime (sin cambios de código):
  - `rg -n "_load_prompt_literal|read_text\(|prompts_literal_v2|Path\(__file__\).*docs" backend/prompts.py backend/negotiation/elementos/render/executor_prompts.py backend/negotiation`
  - `rg -n "NECESITA_INFO|need_info_slots|planner_need_info_slots" backend/negotiation backend/prompts.py --glob '!backend/tests/**'`
