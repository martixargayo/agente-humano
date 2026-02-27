# 01 — Prompt source of truth (estado actual)

## Claim
Los prompts activos del runtime están hardcodeados en las constantes runtime (sin loader desde `docs/`) y su contenido coincide byte a byte con `docs/prompts_literal_v2/*`.

## Evidence
- `backend/prompts.py` define en literal `SUMMARY_SYSTEM_PROMPT`, `SUMMARY_USER_PROMPT`, `PLANNER_SEMANTIC_V1_SYSTEM_PROMPT` y `PLANNER_SEMANTIC_V1_USER_PROMPT`.
  - Ver bloques literales en `backend/prompts.py` líneas 3–64, 66–103, 156–237 y 239–288.
- `backend/negotiation/elementos/render/executor_prompts.py` define en literal `EXECUTOR_V2_SYSTEM_PROMPT`, `EXECUTOR_V2_USER_PROMPT`, `EXECUTOR_FINALIZER_V1_SYSTEM_PROMPT` y `EXECUTOR_FINALIZER_V1_USER_PROMPT`.
  - Ver `backend/negotiation/elementos/render/executor_prompts.py` líneas 13–97, 99–157, 159–217 y 219–251.
- El runtime consume esos identificadores sin wiring adicional de archivos:
  - Planner usa `PLANNER_SEMANTIC_V1_*` desde `repo_prompts` en `backend/negotiation/phase_policy_planner.py` líneas 11–14 y 226–228.
  - Executor node usa prompts de finalizer desde constantes en `backend/negotiation/nodes/executor_node.py` líneas 22–25 y 175–177.
- Comprobación de ausencia de loader en runtime (sin resultados):
  - `rg -n "_load_prompt_literal|read_text\(|prompts_literal_v2|Path\(__file__\).*docs" backend/prompts.py backend/negotiation/elementos/render/executor_prompts.py backend/negotiation`
- Comprobación byte-identical (resumen de salida):
  - `SUMMARY_SYSTEM_PROMPT: OK`
  - `SUMMARY_USER_PROMPT: OK`
  - `PLANNER_SEMANTIC_V1_SYSTEM_PROMPT: OK`
  - `PLANNER_SEMANTIC_V1_USER_PROMPT: OK`
  - `EXECUTOR_V2_SYSTEM_PROMPT: OK`
  - `EXECUTOR_V2_USER_PROMPT: OK`
  - `EXECUTOR_FINALIZER_V1_SYSTEM_PROMPT: OK`
  - `EXECUTOR_FINALIZER_V1_USER_PROMPT: OK`

## Reasoning
Las constantes se definen inline en los módulos runtime y no hay lectura de `docs/` en código de ejecución. El check de igualdad byte a byte confirma que el texto runtime coincide exactamente con la documentación literal usada como referencia.

## How to reproduce
1. Ver líneas runtime:
   - `nl -ba backend/prompts.py | sed -n '1,320p'`
   - `nl -ba backend/negotiation/elementos/render/executor_prompts.py | sed -n '1,280p'`
2. Ver uso de prompts en planner/finalizer:
   - `nl -ba backend/negotiation/phase_policy_planner.py | sed -n '1,260p'`
   - `nl -ba backend/negotiation/nodes/executor_node.py | sed -n '1,230p'`
3. Ver ausencia de loader:
   - `rg -n "_load_prompt_literal|read_text\(|prompts_literal_v2|Path\(__file__\).*docs" backend/prompts.py backend/negotiation/elementos/render/executor_prompts.py backend/negotiation`
4. Re-ejecutar comparación byte-identical:
   - `PYTHONPATH=backend python - <<'PY' ...comparador de 8 constantes vs docs/prompts_literal_v2... PY`
