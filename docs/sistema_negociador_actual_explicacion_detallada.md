# Sistema negociador actual: explicación detallada

## 1. Qué hace el sistema hoy (visión ejecutiva)

El sistema negociador actual es un **agente conversacional por turnos** orientado a una negociación de compra/venta (caso principal: coche), con un pipeline semántico fijo en cinco pasos:

1. **World node** (juez semántico del turno).
2. **Belief node** (actualización de creencias/señales).
3. **Planner node** (decisión de fase + intención táctica).
4. **Progress node** (persistencia de progreso y ledger).
5. **Executor node** (redacción de respuesta + finalizador de calidad).

El flujo se activa por el endpoint `/negociar`, persiste estado por `user_id + session_id`, guarda trazas de depuración por turno y mantiene una memoria dual (corta + larga) para consistencia conversacional.

---

## 2. Punto de entrada HTTP y ciclo por turno

### 2.1 Endpoint principal

La negociación entra por `POST /negociar`:

- Recupera o crea sesión con `get_session_state(user_id, session_id)`.
- Ejecuta el pipeline con `run_negotiation_agent(state, payload.message)`.
- Opcionalmente encola un refresco de resumen si está activo `NEGOTIATION_DEFER_SUMMARY`.
- Devuelve `reply` al cliente.

Esto significa que **todo el estado vivo de la negociación** se acumula en la sesión: historial, world/belief/progress state, contador de turnos y traza técnica.

### 2.2 Qué pasa dentro de `run_negotiation_agent`

Por cada mensaje nuevo del usuario:

1. Se añade el mensaje al historial y se incrementa `turn_count`.
2. Se prepara el `graph_state` con:
   - mensaje actual,
   - estados persistidos (`world_state`, `belief_state`, `progress_state`),
   - memoria corta/larga,
   - metadatos (phase map, last assistant message, recent history).
3. Se ejecuta el pipeline secuencial (`world -> belief -> planner -> progress -> executor`).
4. Se extrae la respuesta final (`response`) y se añade al historial.
5. Se refresca memoria dual (`memory_short` y `memory_long`) y se guarda meta de resumen.
6. Se persisten de vuelta estados clave y se agrega evento a `debug_trace`.

---

## 3. Arquitectura del pipeline de negociación

## 3.1 World node (`world_updater_node`)

No “simula mundo físico”; en la implementación actual actúa como un **juez semántico**:

- Construye prompt con:
  - mensaje del vendedor (`user_message`),
  - último mensaje del asistente,
  - historial compacto,
  - `semantic_ledger` previo.
- Llama al LLM de planner para clasificar/normalizar salida `judge_semantic_v1`.
- Produce:
  - `topic_alignment` (`on_topic`/`off_topic`),
  - `reason_short`,
  - `semantic_ledger` actualizado,
  - `ledger_update_notes`.
- Si falla parseo/esquema, aplica fallback semántico neutro y marca degradación en meta.

Salida principal del nodo: `state["semantic_judge"]` + `state["world_debug"]`.

## 3.2 Belief node

Se mantiene para compatibilidad de pipeline (estructura de cinco nodos), pero el peso de la lógica actual está en el eje semántico world/planner/progress/executor. Su función es sostener la interfaz de estado y evitar ruptura de contrato entre nodos.

## 3.3 Planner node (`phase_policy_planner_node`)

Es el **cerebro de intención táctica** por turno:

- Calcula `effective_semantic_ledger` fusionando progreso previo + judge actual.
- Registra `effective_ledger_hash` para observabilidad de consistencia.
- Ejecuta `plan_phase_policy(...)` con contexto amplio (memoria, historial, judge, constraints, mensaje actual).
- Produce:
  - `phase_candidate`,
  - `policy_decision`,
  - `planner_semantic_output` (schema `planner_semantic_v1`),
  - metadatos ricos (tokens, latencia, prompts renderizados, fallback flags).

`planner_semantic_output` incluye una guía estructurada (`next_move_hint`) con contrato interno tipo:

- `OBJECTIVE_DELTA`
- `TACTIC`
- `RESPUESTA`
- `MOVIMIENTO`
- `TEMA`

Ese contrato después lo consume el executor/finalizer.

## 3.4 Progress node (`progress_updater_node`)

Este nodo concentra la **persistencia del progreso semántico**:

- Copia estado previo.
- Actualiza `semantic_ledger` con datos del `semantic_judge` del turno.
- Guarda `last_chosen_policy_id` y `last_progress_update_turn`.
- Devuelve también `progress_debug` resumido.

El `semantic_ledger` se organiza en tres listas canónicas:

- `lo_que_ya_se_toco`
- `lo_que_ya_pregunte`
- `lo_que_falta_pero_no_insistire`

Esto reduce repetición y ayuda al control de ritmo conversacional.

## 3.5 Executor node (`executor_node`)

Convierte la intención en texto final negociador:

1. Renderiza un **borrador** con `render_executor_output(...)` usando perfiles (persona/escena/estilo/constraints).
2. Registra telemetría de esa llamada LLM.
3. Opcionalmente pasa por **finalizer** (`NEGOTIATION_EXECUTOR_FINALIZER_ENABLED`):
   - usa prompt específico de finalización,
   - corrige ajuste al diálogo, política de preguntas y brevedad,
   - puede correr en modo `active` o `shadow`.
4. Actualiza `progress_state.phase_state` y bandera `last_executor_asked_question`.
5. Deja la respuesta en `assistant_message`/`response`.

Además deja observabilidad de hashes (`planner_ledger_hash`, `executor_ledger_hash`, `effective_ledger_hash`) para detectar posibles desalineaciones.

---

## 4. Memoria del sistema (short + long)

La memoria no depende solo del historial bruto:

- **Memoria corta (`memory_short`)**: últimas `N` interacciones completas user/assistant (por defecto 4).
- **Memoria larga (`memory_long`)**: resumen acumulado de turnos más antiguos.

### 4.1 Estrategia de actualización

Después de responder:

- Se calcula overflow de turnos fuera de la ventana corta.
- Si hay turnos nuevos por resumir, se llama al summarizer (`deps.summarize`) y se actualiza `memory_long`.
- Se recalcula `memory_short` desde el buffer más reciente.
- Se persiste todo en `progress_state` (`turn_buffer`, `memory_short`, `memory_long`, contadores de turnos resumidos).

Resultado: mantiene contexto útil sin crecer linealmente en tokens por turno.

### 4.2 Modo deferred summary

Si `NEGOTIATION_DEFER_SUMMARY=1`, el refresco de resumen sale del camino crítico del endpoint y se encola como job en segundo plano. Mejora latencia percibida a costa de consistencia eventual de `memory_long` justo tras el turno.

---

## 5. Estado persistido por sesión

Cada sesión (`user_id`, `session_id`) conserva, entre otros:

- `history` (mensajes de chat),
- `turn_count`,
- `world_state`,
- `belief_state`,
- `progress_state`,
- `summary` y `summary_meta`,
- `last_policy_executed`,
- `debug_trace`.

Con esto, cada turno nuevo se ejecuta con continuidad real de negociación y no como inferencia aislada.

---

## 6. Observabilidad y depuración operativa

El sistema trae dos niveles de traza streaming:

1. `/negociacion/trazas/stream` (trace original).
2. `/negociacion/livetrace2/stream` (vista más estructurada por nodo).

Se emiten eventos SSE con payload por nodo (entrada/salida, latencia, estado, decisiones de gate, errores). Esto permite diagnosticar:

- repetición de temas,
- degradaciones de parseo/JSON,
- fallback de planner/judge,
- desfases entre planner y executor,
- impacto de configuración de finalizer.

---

## 7. Decisiones de diseño que definen el “sistema actual”

1. **Pipeline determinista de nodos** (no rutas dinámicas): facilita depuración y control de calidad.
2. **Ledger semántico como fuente de verdad conversacional** para evitar insistencia/repetición.
3. **Planner y Executor desacoplados** por contrato textual estructurado (`next_move_hint`).
4. **Finalizer como segunda pasada de control** para mejorar ajuste humano de respuesta.
5. **Memoria dual** para balance entre costo/token y continuidad narrativa.
6. **Telemetría rica** (prompts renderizados, tokens, hashes) para iteración rápida de producto.

---

## 8. Configuración crítica (variables de entorno)

- `NEGOTIATION_DEFER_SUMMARY`: activa resumen diferido por cola.
- `NEGOTIATION_EXECUTOR_FINALIZER_ENABLED`: habilita/deshabilita finalizer.
- `NEGOTIATION_EXECUTOR_FINALIZER_MODE`: `active` o `shadow`.
- `NEGOTIATION_MEMORY_SHORT_TURNS`: tamaño de memoria corta.
- `NEGOTIATION_TURN_BUFFER_MARGIN`: margen extra del buffer persistido.

Además existen aliases migrados al arranque para compatibilidad de nombres legacy en `app.py`.

---

## 9. Riesgos y límites prácticos del sistema en su estado actual

1. **Dependencia fuerte de contratos JSON**: cuando un LLM rompe esquema, se entra en fallback (seguro, pero menos fino).
2. **Calidad sensible al prompting**: cambios pequeños en prompts pueden alterar ritmo conversacional.
3. **Consistencia eventual con deferred summary**: puede haber brecha temporal entre turno y resumen largo consolidado.
4. **Acoplamiento a telemetría propia**: muy útil, pero requiere disciplina para mantenerla alineada con cambios de nodos.

---

## 10. Resumen corto (para compartir con equipo)

Tu sistema negociador actual funciona como una **cadena semántica de decisión + ejecución** por turno, con memoria dual y observabilidad profunda. Primero entiende “qué ya se dijo y qué no conviene repetir” (ledger), luego decide fase y táctica (planner), y finalmente genera una respuesta humana controlada por reglas de estilo y un finalizador. Todo queda persistido por sesión y trazado por SSE para diagnóstico fino.
