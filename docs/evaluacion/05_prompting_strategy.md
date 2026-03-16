# 05 — Estrategia de prompting (operativa)

## Versión vigente

- `core_evaluator_prompt.txt` y `trajectory_evaluator_prompt.txt` están alineados con contratos simplificados.
- Mensaje `user` contiene únicamente el subinput serializado entre `BEGIN_INPUT_JSON/END_INPUT_JSON`.

## Reglas activas

### Core evaluator

- Analiza con primacía del diálogo.
- Devuelve solo campos del `feedback_report_core.v1` vigente.
- No devuelve `stars_0_5`, `strengths_to_repeat`, `next_focus`, `recommended_closing_phrase`.
- Recomendaciones con visión global, posibilidad de `0` recomendaciones y `example` opcional.
- Evitar sobre-recomendación y relleno artificial.

### Trajectory evaluator

- Puntúa cada turno con visión global de la secuencia completa.
- Devuelve serie de score + extractos + explicación breve + pensamiento del otro + mejora opcional.
- No devuelve `direction`, color ni derivados calculables.
- Evita metaseñales innecesarias y sobreexplicación.

## Derivación por código (fuera del prompt)

- Estrellas desde `score_global_100`.
- Subida/bajada por comparación entre puntos consecutivos.
- Color de línea/punto por rangos de score.

## Parámetros runtime

- `model`: `gpt-5.4`
- `text.format.type`: `json_schema`
- `text.format.strict`: `true`
- `store`: `false`
- `reasoning.effort`: `medium`
