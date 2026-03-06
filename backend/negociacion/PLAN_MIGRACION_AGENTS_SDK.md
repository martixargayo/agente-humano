> Estado: implementado en esta rama (migración aplicada en pipeline de `negociacion`).

# Plan de implementación: equivalencia literal con cookbook de OpenAI (Agents SDK Sessions)

## Objetivo

Lograr en `negociacion` una implementación **literalmente alineada** con el patrón recomendado en el cookbook de OpenAI:

1. Memoria basada en **Sessions nativas del Agents SDK** (no capa custom).
2. Estrategia híbrida de **trimming + summarization** con límites explícitos por turnos.
3. Prompts de resumen/planning/execution cerrados y estables para dominio negociación.
4. Evals de memoria para demostrar equivalencia funcional (coherencia, retención, costo y precisión).

---

## Estado actual y gap exacto

### Lo que ya existe
- Pipeline `summarizer -> planner -> executor`.
- Recorte por turnos + inyección de bloque sintético de resumen.
- Parámetros `context_limit` y `keep_last_n_turns` por flujo.

### Gap para “equivalencia literal”
- La memoria actual es `SessionMemoryManager` propio (no `SessionABC` del Agents SDK).
- Prompts de `negociacion` aún en placeholder.
- No hay harness de evals específico de memoria para comparar baseline vs migración.

---

## Alcance (in-scope)

- Migrar memoria de `negociacion` a sesión nativa de Agents SDK.
- Mantener el contrato externo del endpoint `/negociar`.
- Definir prompts productivos de negociación.
- Añadir pruebas de regresión de memoria y calidad.
- Añadir observabilidad mínima para auditar summaries.

## Fuera de alcance (out-of-scope)

- Reescribir el flujo de `chat` (se aborda después de estabilizar `negociacion`).
- Cambios de front-end/avatar.
- Replantear modelos base sin datos de eval.

---

## Arquitectura objetivo

### A. Memoria nativa con Agents SDK
- Introducir dependencia `openai-agents`.
- Implementar una sesión de memoria conforme a la interfaz del SDK:
  - Opción 1 (preferida): adaptar y reutilizar una implementación estilo `SummarizingSession` (con `keep_last_n_turns` + `context_limit`).
  - Opción 2: usar sesión nativa simple + componente de resumen enchufable si la API actual del SDK lo favorece.
- Mantener metadata para observabilidad (`synthetic`, `kind`, `summary_for_turns`) sin enviarla al modelo cuando no corresponda.

### B. Integración con el pipeline actual
- Crear un adaptador `negociacion/session_adapter.py` que encapsule:
  - inicialización de sesión por `(user_id, session_id)`,
  - carga/guardado de estado persistente en `world_state`,
  - utilidades para `get_items()` (model-safe) y `get_full_history()` (debug).
- Reemplazar el uso de `SessionMemoryManager` dentro de `run_three_llm_turn` sólo para el flujo `negociacion` en primera etapa (feature flag).

### C. Prompts cerrados de negociación
- Definir prompts finales en:
  - `backend/negociacion/prompts/summarizer_prompt.txt`
  - `backend/negociacion/prompts/planner_prompt.txt`
  - `backend/negociacion/prompts/executor_prompt.txt`
- El prompt de summary debe incluir secciones estructuradas y reglas anti-hallucination:
  - Contexto/objetivo,
  - estado de concesiones y límites,
  - hitos temporales,
  - contradicciones,
  - blockers,
  - next best action,
  - campos `UNVERIFIED`.

### D. Evals de equivalencia
- Construir set de transcripciones de negociación (corto, medio, largo).
- Métricas mínimas:
  - Retención de restricciones (precio tope, BATNA, plazos, no-go terms),
  - No contradicción inter-turno,
  - Precisión de entidades/valores,
  - Tasa de repetición innecesaria,
  - Tokens/latencia por turno.
- Criterio de salida: paridad o mejora frente baseline en calidad con costo controlado.

---

## Plan por fases

## Fase 0 — Diseño y seguridad de migración (1 día)

### Tareas
- Definir feature flag: `NEGOTIATION_USE_AGENTS_SESSION=true|false`.
- Diseñar interfaz de sesión para no romper endpoint actual.
- Definir contratos de serialización de memoria al `world_state`.

### Entregables
- ADR corto (`docs/adr/`) con decisión técnica y rollback.
- Checklist de compatibilidad.

### Criterio de aceptación
- Puede activarse/desactivarse la nueva memoria sin cambiar API externa.

---

## Fase 1 — Implementación de sesión nativa (2-3 días)

### Tareas
- Añadir `openai-agents` a `backend/requirements.txt`.
- Crear `backend/negociacion/session_memory.py` con implementación nativa:
  - trimming por turnos,
  - summarization al superar límite,
  - bloque sintético user/assistant.
- Añadir persistencia en `state.world_state["negotiation_memory"]`.

### Entregables
- Código de sesión + tests unitarios de:
  - detección de turnos reales,
  - boundary correcto,
  - idempotencia al resumir,
  - preservación de últimos N turnos.

### Criterio de aceptación
- Todos los tests unitarios de memoria en verde.

---

## Fase 2 — Integración en pipeline negociación (1-2 días)

### Tareas
- Integrar la sesión nativa en `run_negotiation_agent`/pipeline bajo feature flag.
- Mantener planner y executor sin romper contrato.
- Añadir logging estructurado de eventos de resumen.

### Entregables
- Pipeline funcionando en modo legacy y modo agents-session.
- Logs con trazabilidad de resúmenes.

### Criterio de aceptación
- Smoke test end-to-end de `/negociar` pasa en ambos modos.

---

## Fase 3 — Prompts finales de negociación (1-2 días)

### Tareas
- Sustituir placeholders por prompts productivos.
- Alinear planner schema con campos de memoria relevantes.
- Añadir ejemplos few-shot mínimos (si aportan estabilidad).

### Entregables
- 3 prompts finales versionados.

### Criterio de aceptación
- Sin uso de fallbacks “PROMPT PENDIENTE DE PEGAR” en negociación.

---

## Fase 4 — Evals y tuning (2-3 días)

### Tareas
- Crear harness de replay de conversaciones de negociación.
- Comparar baseline vs agents-session con mismas conversaciones.
- Ajustar `context_limit` y `keep_last_n_turns` con datos.

### Entregables
- Reporte de métricas (calidad + costo + latencia).
- Recomendación final de parámetros.

### Criterio de aceptación
- Igual o mejor retención de constraints, menor o igual contradicción, costo razonable.

---

## Fase 5 — Rollout controlado (1 día)

### Tareas
- Activación gradual por porcentaje/sesión.
- Monitorización de errores y degradaciones.
- Plan de rollback inmediato al modo legacy.

### Criterio de aceptación
- Estabilidad operativa 48h y métricas dentro de umbral.

---

## Backlog técnico recomendado

- Guardar snapshots de summary con hash/versionado para auditoría.
- Añadir comparación automática entre “summary actual” vs “summary esperado” con LLM-as-judge.
- Añadir test de “context poisoning” (hecho incorrecto introducido y no propagado).

---

## Riesgos y mitigaciones

1. **Drift de summaries**
   - Mitigación: prompt estructurado + evals de contradicción + UNVERIFIED obligatorio.
2. **Aumento de latencia/costo**
   - Mitigación: refresco de resumen solo al exceder límite; modelo resumidor más económico.
3. **Regresiones en comportamiento de negociación**
   - Mitigación: feature flag + replay tests + rollout gradual.
4. **Dependencia nueva (`openai-agents`)**
   - Mitigación: lock de versión y fallback legacy temporal.

---

## Definición de “Done” (equivalencia literal aceptable)

Se considera completado cuando:

- `negociacion` usa sesión nativa del Agents SDK para memoria de conversación.
- La memoria aplica trimming + summarization con reglas explícitas y auditables.
- Los prompts de negociación están cerrados (sin placeholders/fallbacks).
- Existe suite de evals reproducible con comparación baseline vs nuevo sistema.
- El endpoint público mantiene compatibilidad funcional.

