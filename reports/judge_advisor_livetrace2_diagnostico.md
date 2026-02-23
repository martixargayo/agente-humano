# Diagnóstico técnico: world_judge_llm y advisor_llm (LiveTrace2)

Este documento resume hallazgos de wiring, versionado de prompts, latencia y robustez JSON para los nodos `world_judge_llm` y `advisor_llm`.

## Hallazgos clave

1. `world_judge_llm` selecciona v2 **solo** por `USE_WORLD_JUDGE_V2=1` en `os.environ`; no existe otra compuerta por `state` o `progress_state`.
2. `advisor_llm` selecciona v2 **solo** por `USE_ADVISOR_V2=1`.
3. LiveTrace2 no expone explícitamente `USE_WORLD_JUDGE_V2`/`USE_ADVISOR_V2` en `header.env_snapshot`, lo que impide confirmar rápidamente si el proceso que sirvió el turno tenía esos flags activos.
4. La latencia de advisor puede multiplicarse por diseño (secuencia structured output -> json_mode/direct invoke -> repair -> json_mode repair) y usa la config de planner (timeout/retries), por lo que un único turno puede acumular varias llamadas LLM.
5. El repair puede devolver exactamente el mismo texto roto (sha256 igual) porque no existe guardarraíl de “forzar diferencia” antes de aceptar el resultado del mismo `llm`; solo se etiqueta `advisor_reason_code=repair_same_as_initial`.

## Cambios recomendados (resumen)

- Añadir `USE_WORLD_JUDGE_V2` y `USE_ADVISOR_V2` a `LiveTrace2.header.env_snapshot`.
- Registrar metadata por nodo en `trace_runtime.llm_calls` (prompt_variant, parse_strategy, repair_mode_used, payload_chars).
- Propagar `advisor_model` al `record_llm_call_ms` de advisor.
- Añadir presupuestos de intento de advisor (máximo N intentos / deadline global) para evitar colas de ~30s.
- Hacer hard-fail de repair “idéntico al input roto” y cambiar prompt/mode inmediatamente.

