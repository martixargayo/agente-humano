# 05 · Estado canónico y memoria en `conversacion_simple`

## 1) Observación del estado actual

En `negociacion`, `CanonicalState` incluye persona, brief, memoria episódica, memoria de trabajo, estado negociador, planner_state, scene, ui y trace; además se persisten `recent_dialogue` y `traces` por keys en world_state.

Referencias:
- `backend/negociacion/state/canonical_state.py`
- `backend/negociacion/orchestration/flow_config.py` (`StateRepository`)

## 2) ¿Mantener mismo estado o variante?

### Recomendación

Mantener una **variante compatible**:

- conservar estructura general (session/thread/persona/brief/memory/trace/ui),
- reemplazar subestado hiper específico de negociación por `conversation_state` cuando no aplique,
- mantener nombres de alto valor operacional (`memory_working`, `memory_episodic`, `recent_dialogue`, `openai_thread`).

## 3) Campos mínimos imprescindibles

1. `session` y `openai_thread`.
2. `persona`.
3. `conversation_brief` (equivalente semántico de `negotiation_brief`).
4. `memory_working` (`current_topic`, `pending_question`, `last_turn_summary`).
5. `memory_episodic`.
6. `conversation_state` (snapshot operativo).
7. `ui_state`.
8. `trace_state`.

## 4) Actualización de estado post-turn

Con 1 LLM:

1. se parsea `BrainOutput`,
2. se aplica patch a estado canónico,
3. se agrega turno a `recent_dialogue`,
4. se trimea ventana reciente,
5. se guarda trace.

## 5) Trimming + summarization (requisito central)

## 5.1 Trimming ventana corta

Mantener `recent_dialogue` con límite fijo (`max_recent_messages`) igual que hoy.

## 5.2 Summarization histórica

Propuesta recomendada:

- `memory_episodic` conserva eventos estructurados recientes.
- Al superar umbral (`episodic_threshold`), mover bloque antiguo a `memory_compacted_summary`.
- Compresión preferida fuera del camino crítico (job diferido) para conservar 1-LLM online.

## 5.3 Modos de compresión

1. **Preferente (diferido con LLM)**
   - no afecta latencia de respuesta.
2. **Fallback determinista**
   - resumen heurístico si job falla o no hay clave.
3. **Inline opcional (desaconsejado baseline)**
   - solo si se activa flag de calidad máxima.

## 6) Política de ventanas propuesta

- `recent_dialogue`: 12 mensajes (como baseline actual) — configurable.
- `recent_episodic`: últimos N eventos de alta resolución.
- `memory_compacted_summary`: resumen acumulado de histórico remoto.

## 7) Riesgos de deriva

1. Resumen demasiado agresivo -> pérdida de compromisos claves.
2. Resumen demasiado laxo -> crecimiento de contexto/coste.
3. Fallback determinista pobre -> incoherencia de turnos largos.

Mitigaciones:
- tests de regresión con conversaciones largas,
- trazas con métricas de compresión (antes/después),
- auditorías en optimizador comparando variantes.

## 8) Observabilidad recomendada

Registrar en trace:

- tamaño de `recent_dialogue` antes/después,
- eventos episódicos añadidos,
- compresión ejecutada (`none|deferred_llm|deterministic`),
- hash y chars de summary compactado,
- reason code de fallback.

## 9) Respuesta a pregunta clave #4

### ¿Cómo mantener estado canónico coherente con una sola LLM?

Con un contrato de salida fuerte (`BrainOutput`) + aplicación determinista de patch en código + validación pydantic estricta + trazas de patch aplicado.

## 10) Respuesta a pregunta clave #5

### ¿Cómo mantener trimming + summarization sin volver a 4 LLMs por turno?

Separando claramente:

- online (1 LLM): decisión/respuesta + patch mínimo,
- offline/diferido: compresión histórica,
- fallback determinista cuando no haya compresión LLM disponible.
