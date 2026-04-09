# Validación fina de `conversacion_simple` (estado actual correcto) — 2026-04-09

Este documento fija una guía operativa para validar el estado actual del flujo `conversacion_simple` sin reabrir hipótesis históricas ya cerradas, salvo nueva evidencia.

## Premisa de trabajo

Partimos del estado vigente como **correcto**:

- Núcleo único por turno: `run_conversacion_simple_turn(...)`.
- Una sola LLM principal por turno (`gpt-5.4`).
- Summarizer separado para memoria larga (`gpt-5.4-nano`) bajo umbral.
- Provider stateless (`store=False`, sin `conversation_id`, sin `previous_response_id`).
- Structured Outputs (`BrainOutput`) en strict mode activo.
- Assets ricos (`persona`, `conversation_brief`, `phase_cards`) preservados end-to-end.
- Trazas compactas en modo normal y forense opt-in vía `CONVERSACION_SIMPLE_TRACE_FORENSIC=1`.

## Objetivos de esta fase

1. Verificar comportamiento real del flujo actual (no forense de incidentes pasados).
2. Medir calidad de salida y estabilidad de `BrainOutput`.
3. Confirmar paridad funcional entre `interfaz_usuario` y `optimizador` cuando la comparación es válida.
4. Detectar contaminación de estado entre superficies o sesiones.
5. Vigilar residuos/cascadas de observabilidad fuera de modo forense.

## Matriz mínima de validación continua

### A. Contrato de runtime single-LLM

- Brain model objetivo: `gpt-5.4`.
- Summarizer model objetivo: `gpt-5.4-nano`.
- `pipeline_topology = single_llm` y `node_names = ["brain"]` en el turno base.

### B. Provider stateless

- En requests del brain/summarizer:
  - `store=False`.
  - ausencia explícita de `conversation_id`.
  - ausencia explícita de `previous_response_id`.

### C. Assets ricos end-to-end

- Confirmar que `persona`, `conversation_brief`, `phase_cards`:
  - se cargan del contexto real (`negociacion_sala_reuniones`),
  - llegan íntegros al `brain_input_json`,
  - y no son degradados por loaders intermedios.

### D. Paridad entre superficies

Comparar `interfaz_usuario` vs `optimizador` solo cuando:

- mismo `context_id`,
- estado/sesión alineados,
- sin overrides relevantes.

Validar señal de comparabilidad:

- `comparable_to_interfaz_usuario_base=true`, `comparability_reason=no_overrides`.
- Si hay overrides en optimizador: `comparable_to_interfaz_usuario_base=false`, `comparability_reason=overrides_applied`.

### E. Higiene de trazas

- En modo normal, mantener señales compactas de resultado, fallback y latencia.
- Confirmar que payloads pesados (`*_provider_request`, `*_provider_response_text`, `schema_serialized`) no se persisten salvo modo forense.

## Batería recomendada (rápida)

Ejecutar de forma recurrente:

1. `backend/tests/test_conversacion_simple_provider_stateless.py`
2. `backend/tests/test_conversacion_simple_asset_passthrough_runtime.py::test_brain_provider_request_keeps_rich_assets_for_interfaz_y_optimizador`
3. `backend/tests/test_conversacion_simple_phase3_surface_tooling.py::test_optimizador_sandbox_turn_routes_to_conversacion_simple`
4. `backend/tests/test_conversacion_simple_phase3_surface_tooling.py::test_optimizador_marks_non_comparable_when_conversacion_simple_has_overrides`
5. `backend/tests/test_conversacion_simple_vs_negociacion_trace_contracts.py::test_trace_envelope_has_external_contract_and_deliberate_node_divergence`

## Criterios de aceptación para esta etapa

Se considera **verde** si:

- no hay fallback inesperado en casos nominales,
- se mantiene `BrainOutput` válido en flujo normal,
- no aparece continuidad provider stateful,
- no reaparecen assets degradados,
- y las diferencias entre superficies son explicables por comparabilidad (no por skew oculto).

## Protocolo si aparece nueva evidencia

1. Capturar evidencia mínima reproducible (caso, contexto, traza y fecha/hora UTC).
2. Clasificar si el desvío es:
   - contrato,
   - datos de contexto,
   - estado/sesión,
   - o observabilidad.
3. Solo entonces abrir rama de diagnóstico forense (opt-in) con `CONVERSACION_SIMPLE_TRACE_FORENSIC=1`.
4. Cerrar con hipótesis falsables y prueba de no regresión.
