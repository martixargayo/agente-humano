# Documento 3 — Integración del nuevo nodo LLM: EXECUTOR_FINALIZER_V1

## Objetivo
Insertar `EXECUTOR_FINALIZER_V1` para corrección final de encaje, agencia y brevedad, manteniendo schema `executor_v2`.

## Pipeline objetivo
1. `executor_llm` produce draft `executor_v2`.
2. `schema_validator` valida draft.
3. `executor_finalizer_llm` procesa draft + contexto.
4. `schema_validator` valida salida final.
5. Entrega `executor_v2` final.

## Contrato de entrada al finalizer
1. Draft:
   - `executor_draft_json`
2. Plan:
   - `planner_semantic_output_json`
   - `objective_delta` parseado
   - `tactic` parseado
   - `topic_selected`
   - `phase`, `prev_phase`
3. Contexto conversacional:
   - `last_seller_utterance`
   - `user_message`
   - `assistant_last_message`
4. Memoria:
   - `memory_short_compact`
   - `memory_long_compact`
   - `semantic_ledger_json`
5. Restricciones:
   - `max_words`
   - `target_words`
   - `max_questions`
   - `prev_turn_asked_question`

## Contrato de salida del finalizer
1. Solo JSON `executor_v2`.
2. Sin claves fuera del schema oficial.
3. Sin retries: una sola llamada LLM por turno.

## Precedencias para evitar doble corrección
1. Correcciones de estilo/encaje/brevedad pasan a ser responsabilidad principal del finalizer.
2. Validadores deterministas mantienen responsabilidad de:
   - integridad de schema
   - consistencia estructural mínima
3. Correcciones legacy “soft” del executor deben desactivarse o reducirse cuando finalizer esté activo para evitar sobreescritura doble.
4. Si finalizer está desactivado, mantener comportamiento actual como fallback.

## Feature flag conceptual
1. `executor_finalizer_enabled`:
   - `false`: pipeline actual sin finalizer.
   - `true`: pipeline con finalizer posterior a executor.
2. `executor_finalizer_mode`:
   - `shadow`: finalizer corre en paralelo para logging, sin afectar respuesta.
   - `active`: finalizer reemplaza salida del executor.

## Plan A/B
1. A (control): `executor_finalizer_enabled=false`.
2. B (tratamiento): `executor_finalizer_enabled=true`, modo `active`.
3. Métricas de comparación:
   - latencia por turno
   - longitud media de respuesta
   - tasa de preguntas
   - encaje con último mensaje del vendedor
   - incidencia de salidas corregidas por schema

## Dependencias afectadas
1. `backend/negotiation/negotiation_graph.py` (orden de nodos)
2. `backend/negotiation/nodes/executor_node.py` (etapa de salida)
3. `backend/negotiation/executor/render_executor.py` (señales compartidas)
4. `backend/negotiation/telemetry/trace_runtime.py` (registro llm_call finalizer)
