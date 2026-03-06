# Decisiones cerradas — Iteración 3 (runtime y cierre de arquitectura)

## 1) Bootstrap real de `conversation`
- Se implementó `bootstrap_conversation_if_needed(client, canonical_state)`.
- Si el modo es `conversation` y no hay `conversation_id`, se crea explícitamente conversación vía API y se persiste el `id` en estado canónico.
- No se recrea si ya existe.
- Si no hay cliente, se registra y se mantiene fallback limpio.

## 2) Structured outputs con clasificación explícita de resultado
- Se introdujo `StructuredCallResult` con:
  - `parsed_json`
  - `refusal`
  - `parse_error`
  - `exception_error`
  - `response`
  - `source` (`model|refusal|fallback|parse_error|exception`)
- Refusal del modelo ya no se mezcla con parse errors ni con fallback local.

## 3) No-replan del executor (enforcement real)
- Se aplica **hard baseline** siempre activa:
  - si `conversation_act_realized` != `planner.policy.conversation_act`,
  - se reemplaza `spoken_text` por texto seguro y neutro de `clarify`,
  - se marca `refusal_reason=executor_replan_blocked`.
- Resultado final coherente tanto en metadata como en texto emitido.

## 4) `feature_safety` gobierna capa opcional de verdad
- Política explícita en código:
  - **hard baseline**: siempre on (incluye no-replan)
  - **optional safety layer**: gobernada por `feature_safety`
- Cuando `feature_safety=False`, se desactiva capa opcional (PII/overclaim/domain guardrails), pero baseline duro sigue activo.

## 5) Planner reequilibrado
- Se enriqueció `ConversationAct` con:
  - `acknowledge`, `answer`, `ask_clarification`, `ask_followup`, `propose`, `refuse`.
- `PlannerStyleBand` incluye ahora:
  - `tone`, `length_band`, `directness`, `initiative`, `emotional_intensity`.
- `PlannerLimits` incluye ahora:
  - `max_sentences`, `max_questions`, `allow_topic_shift`, `allow_advice`, `allow_personal_disclosure`.
- Executor recibe esta riqueza en `planner_output` sin abrir superficie para replanificar.

## 6) User turn tipado
- Se introdujo `UserTurn` y se usa en memory/planner/executor inputs.
- Campos: `raw_text`, `normalized_text`, `modality`, `language`, `timestamp_utc`.

## 7) Compatibilidad SDK con enforcement real
- Se introdujo `check_openai_sdk_compatibility()`.
- Registra estado de compatibilidad y permite modo estricto (`enforce_sdk_compatibility`) para fallar si está por debajo del mínimo.
- La traza guarda `sdk_compatibility` estructurado.

## 8) `load_state` seguro
- Si falla validación de estado persistido:
  - se loguea error estructurado,
  - se hace fallback explícito a estado por defecto.
- Ya no hay reset silencioso.

## Lo único que queda antes de prompts finales
1. Afinado de prompts finales por nodo (estilo/tono/ejemplos).
2. Rúbricas de eval definitivas (hoy hay hooks estructurados).
3. Migración a persistencia externa (Redis/Postgres) cuando se decida.
