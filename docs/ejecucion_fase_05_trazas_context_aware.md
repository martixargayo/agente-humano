# Ejecución Fase 05 — trazas context-aware

## Qué cambió exactamente

Se añadió metadata contextual aditiva a las trazas de turno y al `_entry_contract`, sin tocar la lógica de negociación ni el bundle efectivo baseline.

## Metadata nueva

Se añadió `context_meta` con estas claves:

- `flow_id`
- `context_id`
- `context_version`
- `official_context_used`
- `context_scope` (`official` u `official_with_overrides`)

## Dónde vive ahora

- en cada `TurnTrace` persistida
- en `_entry_contract.context_meta`
- en `_optimizador.base_context` cuando el turno viene del optimizer

## Archivos tocados

- `backend/negociacion/traces/models.py`
- `backend/negociacion/traces/context_meta.py`
- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/orchestration/turn_contract.py`
- `backend/negociacion/optimizador/services.py`
- `backend/negociacion/optimizador/trace_reader.py`
- `backend/tests/test_phase5_context_traces.py`
- `backend/scripts/check_phase5_context_traces.py`
- `docs/ejecucion_fase_05_trazas_context_aware.md`

## Qué no se tocó

- prompts efectivos
- JSON efectivos
- planner/executor/memory/phase classifier
- canonical state táctico
- finish_button_armed
- evaluación context-aware
- optimizer context-aware completo

## Compatibilidad

La compatibilidad se garantiza porque `context_meta` es opcional en `TurnTrace`. Las trazas legacy siguen validando aunque no tengan esos campos.

## Tests corridos

- `PYTHONPATH=backend python -m unittest backend/tests/test_phase5_context_traces.py`
- `PYTHONPATH=backend python backend/scripts/check_phase5_context_traces.py`

## Por qué esto cierra Fase 5

Porque cada turno persistido ya identifica explícitamente el contexto oficial usado y esa identidad también aparece en la metadata de entrada y en la metadata propia del optimizer, sin alterar cómo negocia el sistema.

## Qué NO entra todavía

Esto no implementa Fase 6 ni Fase 7:

- no hay evaluación context-aware
- no hay selector completo de contextos en optimizer
- no hay cambios de motor ni de prompts
