# P1 — Prompt Priority: responder preguntas del usuario primero (sin estado nuevo)

## 1) Síntoma + referencia LiveTrace
- Turno 14: el usuario pregunta directamente (“por qué te interesa / qué ofreces”) y el bot pivota a precio.
- Referencia base: `../03_preguntas_directas_ignoradas_sin_pending_queue.md`.

## 2) Objetivo / Definition of Done
**Objetivo:** priorizar respuesta humana a la pregunta directa del usuario antes de abrir nueva exploración.

**DoD**
- `ignored_direct_question_rate` < 3%.
- Aumento de `human_first_semantic_score` medido por LLM-judge.
- Sin introducir `pending_counterparty_questions` como estado nuevo obligatorio.

## 3) Propuesta (centrada en prompt changes)

### 3.1 Planner: prioridad explícita de siguiente movimiento
**Ruta:** `backend/prompts.py` (`PLANNER_SEMANTIC_V1_SYSTEM_PROMPT` y/o `PLANNER_SEMANTIC_V1_USER_PROMPT`).

**Texto exacto sugerido**

```text
HUMAN_FIRST_PRIORITY:
- Si USER_MESSAGE contiene una pregunta directa al asistente, tu next_move_hint DEBE empezar por responder esa pregunta.
- No priorices pedir precio/estado si primero falta responder lo que el usuario acaba de preguntar.
- Después de responder, puedes sugerir un único puente breve para avanzar la conversación.
```

### 3.2 Executor: responder primero, luego puente opcional
**Ruta:** `backend/negotiation/elementos/render/executor_prompts.py` (`EXECUTOR_V2_SYSTEM_PROMPT`).

**Texto exacto sugerido**

```text
[HUMAN-FIRST PRIORITY — APLICACIÓN]
- Si el usuario te hace una pregunta directa, responde esa pregunta en primer lugar, de forma clara y natural.
- Solo después, si aporta valor, añade una frase puente o una única pregunta breve.
- Evita cambiar de tema antes de responder lo preguntado.
```

## 4) Ejemplos antes/después
### Antes
Usuario: “¿Por qué te interesa y qué estás dispuesto a ofrecer?”
Asistente: “¿Qué precio tienes en mente?”

### Después
Usuario: “¿Por qué te interesa y qué estás dispuesto a ofrecer?”
Asistente: “Me interesa porque busco ese modelo y valoro su estado. Si te encaja, te propongo movernos en un rango razonable según lo que ya comentamos.”

## 5) Plan de pruebas (replay) y métricas
- Replay de turnos con preguntas directas explícitas e implícitas.
- LLM-judge semántico:
  1) ¿Respondió la pregunta principal del usuario?
  2) ¿Mantuvo coherencia y tono natural?
- Métricas:
  - `ignored_direct_question_rate`
  - `answer_before_ask_rate`
  - `naturalness_score`

## 6) Riesgos y tradeoffs
- Riesgo: sobrerregular prompt y volver respuestas demasiado formulaicas.
- Mitigación: lenguaje de prioridad, no plantilla rígida.
- Tradeoff: puede reducir iniciativa de negociación en algunos turnos, pero mejora coherencia humana.

## 7) Checklist implementación futura
- [ ] Insertar bloque `HUMAN_FIRST_PRIORITY` en planner prompt.
- [ ] Insertar bloque de aplicación human-first en executor prompt.
- [ ] Ejecutar replay y medir ignorado de preguntas.
- [ ] Ajustar wording para conservar naturalidad.
