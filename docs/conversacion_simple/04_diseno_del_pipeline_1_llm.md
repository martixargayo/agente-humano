# 04 · Diseño del pipeline 1-LLM (documento central)

## 1) Definición exacta de “1 LLM online”

Se considera cumplimiento cuando, en el camino crítico de `turn`:

1. se hace una sola invocación de modelo para resolver la intención del usuario,
2. esa llamada produce tanto contenido visible como artefactos estructurados de estado necesarios,
3. no existe una segunda llamada de memory/phase/executor para completar el turno.

## 2) Responsabilidades que absorbe el nodo único (`brain`)

El `brain` absorbe:

- rol de planner: decisión táctica, límites, siguiente paso;
- rol de executor: texto final al usuario;
- rol parcial de memory: actualización de memoria de trabajo y patch episódico;
- rol parcial de phase_classifier: fase actual (si el flujo la sigue usando).

## 3) Input recomendado al nodo único

### 3.1 Developer prompt fuerte

Debe definir:
- identidad operativa,
- invariantes de seguridad,
- contrato JSON de salida,
- prioridad: exactitud de schema sobre creatividad.

### 3.2 User payload estructurado

Propuesta de input:

- `schema_version`
- `task_contract`
- `user_turn`
- `recent_dialogue_short`
- `memory_working`
- `memory_compacted_summary` (si existe)
- `state_snapshot` (negotiation/conversation state)
- `persona_policy` y `persona_expressive`
- `conversation_brief` (análogo a `negotiation_brief`)
- `phase_assets` (si aplica)
- `trace_meta`

## 4) Output estructurado recomendado

Propuesta de `BrainOutput`:

```json
{
  "schema_version": "brain.v1",
  "status": "deliver|clarify|refuse",
  "assistant_response": {
    "text": "..."
  },
  "state_patch": {
    "phase": "...",
    "turn_goal": "...",
    "conversation_state": {"...": "..."},
    "memory": {
      "working": {"current_topic": "...", "pending_question": null, "last_turn_summary": "..."},
      "episodic_append": [{"event_type": "important_fact", "event_summary": "...", "turn_id": "..."}]
    }
  },
  "limits": {
    "max_sentences": 3,
    "max_questions": 1
  },
  "observability": {
    "confidence": "low|medium|high",
    "safety_notes": []
  }
}
```

## 5) Alternativas comparadas

## Alternativa A — 1 llamada, todo inline (recomendada)

- Online: 1 llamada `brain`.
- Memoria histórica: trimming determinista inmediato + compresión diferida.
- Ventaja: cumple objetivo de latencia/coste y mantiene estado rico.
- Riesgo: prompt/output más complejo (se mitiga con schema estricto + tests).

## Alternativa B — 1 llamada online + 1 llamada post-turn síncrona de compresión

- Strictamente el camino crítico ya no es 1 LLM “puro” si se bloquea respuesta.
- Mejora calidad de resumen, empeora latencia.
- No recomendada como baseline.

## Alternativa C — 1 llamada online + compresión totalmente determinista

- Latencia excelente, coste bajo.
- Riesgo alto de pérdida semántica en historiales complejos.
- Útil como fallback de seguridad, no como estrategia única.

## 6) Recomendación

Adoptar **Alternativa A (híbrida)**:

1. 1 LLM en camino crítico,
2. respuesta inmediata al usuario,
3. update de estado en el mismo output,
4. compresión histórica fuera del camino crítico (scheduler o trigger por umbral),
5. fallback determinista si compresión diferida falla.

## 7) Separación contenido visible vs metadatos

- `assistant_response.text` se muestra al usuario.
- `state_patch` se consume internamente para persistencia.
- `observability` nutre trazas/debug, no UI final.

## 8) Qué pasa con nodos antiguos

- `memory`: absorbido (no llamado online separado).
- `phase_classifier`: absorbido opcionalmente.
- `planner`: evoluciona a `brain` (núcleo único).
- `executor`: absorbido.

## 9) Respuesta a pregunta clave #9

### ¿Recomendación final de diseño y por qué?

Diseño de nodo único `brain` con salida estructurada rica, porque maximiza coherencia con el sistema existente (stateful+contractual) mientras reduce costo/latencia operativa del pipeline.

## 10) Respuesta a pregunta clave #10

### Decisión más delicada

Definir la política de compresión histórica (calidad vs latencia vs pureza de 1-LLM online). Es el punto con mayor impacto en deriva de contexto a medio plazo.
