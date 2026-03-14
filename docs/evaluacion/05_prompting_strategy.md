# 05 — Estrategia de prompting (operativa)

## 0) Decisión de modelo v1 (cerrada)

- `feedback_report_core_v1` → `gpt-5.4`
- `turn_trajectory_v1` → `gpt-5.4`

(Optimización de coste/rendimiento se evalúa en fases posteriores, sin cambiar contratos.)

## 1) Principio obligatorio de separación

Cada invocación usa:

- `developer`: reglas, rúbrica, scoring, restricciones y criterios de éxito.
- `user`: solo input de tarea serializado (bundle/subinput), sin business logic.

## 2) Reglas de contenido por rol

## Developer message (sí debe incluir)

- objetivo exacto del runner,
- definiciones operativas de cada campo de salida,
- rúbrica y reglas de scoring,
- constraints de evidencia (solo diálogo),
- política ante evidencia ausente,
- prohibición de inventar turnos/quotes,
- formato de salida estricto.

## Developer message (NO incluir)

- datos concretos de una sesión específica,
- metadatos variables por ejecución.

## User message (sí debe incluir)

- JSON del subinput concreto para el runner,
- delimitado y con schema_version.

## User message (NO debe incluir)

- criterios de negocio,
- explicación de la rúbrica,
- reglas de scoring,
- instrucciones de estilo generales.

## 3) Delimitadores exactos recomendados

Formato user message:

```text
BEGIN_INPUT_JSON
{ ...subinput json... }
END_INPUT_JSON
```

## 4) Plantilla operativa — Core evaluator

## `core_evaluator_prompt.txt` (developer)

```text
[ROLE]
Eres el evaluador estructurado de desempeño del usuario en negociación.

[OBJECTIVE]
Generar únicamente `feedback_report_core_v1` válido.

[EVIDENCE POLICY]
- Basa el juicio en la evidencia del diálogo por turnos.
- No uses trazas internas como fundamento principal.
- Si falta evidencia, reduce confianza y usa explicaciones conservadoras.

[SCORING RUBRIC]
- Bloque 1: comprension_exploracion ...
- Bloque 2: comunicacion_clima ...
- Bloque 3: movimiento_tactico ...
- Bloque 4: cierre_avance ...
- score_global_100 consistente con bloques.

[TURN REFERENCE RULES]
- Solo puedes citar turn_index existentes.
- Está prohibido inventar turnos, frases o hechos.

[ABSENCE OF EVIDENCE]
- Si no hay evidencia suficiente, usa veredicto conservador y explica "evidencia insuficiente".

[OUTPUT CONTRACT RULES]
- Responde solo JSON válido de `feedback_report_core_v1`.
- No añadas texto fuera del JSON.
- Todos los campos obligatorios.
```

## User template (core)

```text
BEGIN_INPUT_JSON
{
  "schema_version": "core_runner_input.v1",
  "evaluation_id": "...",
  "conversation": { "turns": [...] },
  "conversation_stats": {...},
  "derived_facts": {...},
  "rubric_config": {...},
  "trace_digest": {... opcional y mínimo ...}
}
END_INPUT_JSON
```

## 5) Plantilla operativa — Trajectory evaluator

## `trajectory_evaluator_prompt.txt` (developer)

```text
[ROLE]
Eres evaluador de trayectoria turno a turno.

[OBJECTIVE]
Generar únicamente `turn_trajectory_v1` válido.

[EVIDENCE POLICY]
- Evalúa cercanía al acuerdo/entendimiento en cada turno.
- Fundamenta cada punto en texto de diálogo observable.

[SCORING RULES]
- agreement_closeness_score_0_100 por turno.
- delta_vs_previous = score(turno_actual) - score(turno_previo).
- direction: up si delta>0, flat si delta=0, down si delta<0.

[ANTI-HALLUCINATION]
- Prohibido inventar turnos o citas.
- `user_excerpt` y `counterpart_excerpt` deben derivarse del turno real.

[ABSENCE OF EVIDENCE]
- Si un turno no permite inferencia fuerte, usa impacto neutro (`flat`) y explicación conservadora.

[OUTPUT CONTRACT RULES]
- JSON estricto `turn_trajectory_v1`.
- Sin texto adicional.
```

## User template (trajectory)

```text
BEGIN_INPUT_JSON
{
  "schema_version": "trajectory_runner_input.v1",
  "evaluation_id": "...",
  "turns_for_trajectory": [...],
  "derived_facts_min": {...},
  "trace_digest": {... opcional y mínimo ...}
}
END_INPUT_JSON
```

## 6) Parámetros de invocación recomendados

- `model`: `gpt-5.4`
- `text.format.type`: `json_schema`
- `text.format.strict`: `true`
- `store`: `false`
- `reasoning.effort`: `medium` (core), `medium` (trajectory) en v1 para consistencia de calidad.

## 7) Registro de provenance por invocación

Guardar por runner:

- `evaluation_id`
- `runner_name`
- `model`
- `prompt_version`
- `prompt_hash`
- `input_hash`
- `output_hash`
- `schema_name`
- `latency_ms`
- `validation_result`

Esto alinea prompts con estrategia eval-driven y debugging reproducible.
