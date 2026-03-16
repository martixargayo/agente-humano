# 03 — Contratos

## Resumen de la versión simplificada (vigente)

- Las LLMs **no reciben** `derived_facts` ni `trace_digest` en inputs de runner.
- El core output elimina campos derivados/no esenciales (`stars`, `strengths`, `next_focus`, `closing_phrase`).
- La trayectoria elimina derivados (`direction`, color, agregados resumen) y conserva serie + explicación local.
- Recomendaciones pasan a formato semántico unitario (`title`, `description`, `example?`).
- Derivados visuales se calculan por código (backend/render): estrellas, subida/bajada, color.

---

## 1) `feedback_input_bundle.v1` (interno)

Se mantiene como bundle interno para extracción/adaptación real+demo:

- `schema_version`, `evaluation_id`, `session_ref`
- `conversation.turns[]`
- `conversation_stats`
- `domain_context`
- `derived_facts` y `trace_digest?` solo para uso interno/provenance (no LLM)

## 2) `core_runner_input.v1` (LLM)

Campos vigentes:

- `schema_version`
- `evaluation_id`
- `conversation.turns[]`
- `conversation_stats`
- `domain_context`

> No incluye `derived_facts` ni `trace_digest`.

## 3) `trajectory_runner_input.v1` (LLM)

Campos vigentes:

- `schema_version`
- `evaluation_id`
- `turns_for_trajectory[]`

> No incluye `derived_facts` ni `trace_digest`.

## 4) `feedback_report_core.v1` (LLM core)

Campos vigentes:

- `schema_version`
- `score_global_100`
- `interaction_outcome`
- `summary_2_3_lines`
- `evaluation_blocks[4]` (con checks y block_verdict)
- `best_moment`, `most_delicate_moment`, `turning_point`
- `recommendations[]`
  - `title`
  - `description`
  - `example?`
    - `original_excerpt`
    - `better_rephrase`

## 5) `turn_trajectory.v1` (LLM trayectoria)

Campos vigentes:

- `schema_version`
- `trajectory[]`
  - `turn_index`
  - `agreement_closeness_score_0_100`
  - `user_excerpt`
  - `counterpart_excerpt`
  - `impact_reason`
  - `counterpart_thought_effect`
  - `better_rephrase?`

## 6) `ui_feedback_report.v1` (ensamblado)

- `header` (incluye `stars_0_5` calculado por backend desde `score_global_100`)
- `block_cards`
- `trajectory_chart`
- `key_moments`
- `recommendations.items[]`
- `provenance`

---

## Reglas clave

- Structured outputs con `strict: true`.
- Validación de negocio activa en core/trajectory.
- Reconciliación mantiene cardinalidad/coherencia global sin depender de derivados LLM.
