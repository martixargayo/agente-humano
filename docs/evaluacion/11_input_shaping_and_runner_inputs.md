# 11 — Input shaping y subinputs por runner

## 0) Objetivo

Cerrar operativamente cómo se pasa de `feedback_input_bundle_v1` a los subinputs concretos de:

- runner core (`core_runner_input_v1`)
- runner trajectory (`trajectory_runner_input_v1`)

con control de tamaño, minimización de ruido y primacía del diálogo.

## 1) Política base

1. El diálogo (`conversation.turns`) es la base principal de ambos runners.
2. `derived_facts` entra como apoyo estructurado, no como sustituto del diálogo.
3. `trace_digest` es opcional y reducido (máximo defensivo).
4. Se excluye cualquier payload interno de traza extensa.

## 2) Tabla de mapping bundle → runners

| Campo bundle | Core | Trajectory | Transformación | Motivo |
|---|---|---|---|---|
| `evaluation_metadata` | Sí | Sí | Paso casi directo | Identidad/provenance |
| `conversation.turns` | Sí | Sí | Normalizar índices, truncado por política | Evidencia principal |
| `conversation_stats` | Sí | Parcial | Core completo; trajectory solo `turn_count`/duración | Core sintetiza global |
| `domain_context.final_phase` | Sí | No | Paso directo | Outcome global |
| `domain_context.finish_button_was_armed` | Sí | No | Paso directo | Señal de cierre |
| `derived_facts.offers/concessions/blockers` | Sí | Sí (resumen mínimo) | Compactar listas, limitar longitud | Señal estructural útil |
| `derived_facts.question_patterns` | Sí | Sí | Paso directo corto | Dinámica conversacional |
| `derived_facts.closure_signals` | Sí | No | Paso directo | Cierre global |
| `trace_digest.guardrail_events_count` | Opcional | Opcional | Conteo entero | Contexto defensivo |
| `trace_digest.critical_node_fallback_count` | Opcional | No | Conteo entero | Riesgo técnico (mínimo) |
| `trace_digest.notes[]` | Opcional | No | Máx 3 notas cortas | Evitar ruido |
| `rubric_config` | Sí | No | Paso directo | Core evalúa bloques |

## 3) Campos excluidos explícitamente

No pasan a runners:

- trazas completas por nodo,
- prompts históricos de negociación,
- outputs raw de modelos del pipeline conversacional,
- snapshots completos de canonical state sin reducción.

## 4) Reglas de control de tamaño

## Conversación

- objetivo v1: incluir todos los turnos si `N <= 40`.
- si `N > 40`:
  - mantener siempre primeros 4 y últimos 20,
  - muestrear bloque medio con estrategia por cambios de fase/señales,
  - registrar `input_shaping_log` con turnos retenidos/omitidos.

## Texto por turno

- truncado blando por campo (`user_text`, `assistant_text`) con límite configurable,
- conservar extracto significativo, no recorte ciego de prefijos.

## Derived facts

- limitar listas a top-K por relevancia (configurable, p.ej. 12).

## Trace digest

- tamaño máximo total recomendado: 600 chars serializados.

## 5) Estructura subinput core (`core_runner_input_v1`)

- metadata
- conversación moldeada
- stats globales
- facts derivados compactos
- rúbrica
- trace digest opcional mínimo

## 6) Estructura subinput trajectory (`trajectory_runner_input_v1`)

- metadata
- `turns_for_trajectory[]`
- facts mínimos útiles por turno
- (opcional) guardrail count agregado

## 7) Validaciones de shaping

1. indices estrictamente crecientes y únicos,
2. no huecos inesperados sin `input_shaping_log`,
3. coherencia `turn_count` vs cardinalidad subinput,
4. límites de tamaño respetados.

## 8) Criterio de calidad

Si el shaping elimina evidencia crítica de momentos clave, se considera defecto de implementación y debe corregirse antes de confiar en evals de calidad.
