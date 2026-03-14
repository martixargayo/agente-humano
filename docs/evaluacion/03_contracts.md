# 03 — Contratos

> Norma global (obligatoria): todos los contratos JSON usados con LLM se definen para Structured Outputs con `strict: true`, todos los campos requeridos y `additionalProperties: false` en todos los niveles.

## 0) Principios de diseño de contratos

1. **Primacía del diálogo**: el juicio se basa en turnos usuario/contraparte y su secuencia.
2. **Trazas internas mínimas**: solo señales reducidas y opcionales (`trace_digest`) para soporte defensivo.
3. **Separación análisis/presentación**:
   - LLM produce análisis estructurado (`core`, `trajectory`).
   - backend ensambla contrato UI final (`ui_feedback_report_v1`).
4. **Validación en 3 capas**:
   - schema,
   - reglas de negocio,
   - reconciliación cruzada entre salidas.

---

## 1) `feedback_input_bundle_v1` (generado por código)

## Propósito

Contrato maestro, normalizado y versionado. Fuente única para construir subinputs de cada runner.

## Estructura recomendada

- `schema_version: "feedback_input_bundle.v1"`
- `evaluation_metadata`
  - `evaluation_id`
  - `domain: "negociacion"`
  - `created_at_utc`
  - `session_ref { user_id, session_id }`
- `conversation`
  - `turns[]` (base principal de análisis)
    - `turn_id`
    - `turn_index` (1..N)
    - `user_text`
    - `assistant_text`
    - `timestamp_utc?`
  - `conversation_boundaries`
    - `first_turn_at_utc?`
    - `last_turn_at_utc?`
- `conversation_stats`
  - `turn_count`
  - `duration_seconds`
  - `user_avg_chars`
  - `assistant_avg_chars`
- `domain_context` (negociación)
  - `final_phase?`
  - `finish_button_was_armed`
  - `final_outcome_hypothesis`
- `derived_facts`
  - `offers_detected[]`
  - `concessions_detected[]`
  - `blockers_detected[]`
  - `question_patterns`
  - `closure_signals`
- `trace_digest?` (opcional, reducido)
  - `guardrail_events_count`
  - `critical_node_fallback_count`
  - `notes[]` (máx 3)
- `rubric_config`
  - `blocks[4]` con ids/categorías/pesos

## Política de reducción de trazas (obligatoria)

- `trace_digest` es opcional.
- Nunca incluir payloads completos de trazas por nodo.
- Nunca incluir prompts/raw model outputs previos.
- Nunca usar trazas como base principal de scoring.

---

## 2) `feedback_report_core_v1` (LLM #1)

## Propósito

Evaluación global sintética estructurada (cabecera analítica + bloques + recomendaciones).

## Estructura clave

- `schema_version: "feedback_report_core.v1"`
- `global_assessment`
  - `score_global_100: int`
  - `stars_0_5: number`
  - `interaction_outcome: agreement_reached|partial_progress|no_agreement|blocked`
  - `dominant_pattern_label`
  - `dominant_pattern_explanation`
  - `summary_2_3_lines`
- `evaluation_blocks[4]`
  - `block_id`: `comprension_exploracion|comunicacion_clima|movimiento_tactico|cierre_avance`
  - `status_visual: correcto|mejorable|mal`
  - `score_0_100`
  - `checks[]`
    - `polarity: check|cross`
    - `micro_explanation`
    - `evidence_turn_indexes[]`
  - `block_verdict`
- `key_moments`
  - `best_moment`
  - `most_delicate_moment`
  - `turning_point`
  - cada uno: `turn_index`, `why`, `impact`
- `recommendations`
  - `general[]`
  - `correction_cases[]`
    - `turn_index`
    - `original_excerpt`
    - `better_rephrase`
    - `expected_effect`
- `strengths_to_repeat[]`
- `next_focus`
- `recommended_closing_phrase`

## Reglas de negocio

- `evaluation_blocks` longitud exacta 4.
- `score_global_100` debe ser coherente con promedio ponderado de bloques (tolerancia configurable, p.ej. ±8 puntos).
- Todos los `turn_index` deben existir en conversación.

---

## 3) `turn_trajectory_v1` (LLM #2)

## Propósito

Análisis estructurado turno a turno para visualización de trayectoria y explicación local por turno.

## Estructura clave

- `schema_version: "turn_trajectory.v1"`
- `trajectory[]`
  - `turn_index`
  - `agreement_closeness_score_0_100`
  - `delta_vs_previous`
  - `direction: up|flat|down`
  - `user_excerpt`
  - `counterpart_excerpt`
  - `impact_reason`
  - `counterpart_thought_effect`
  - `better_rephrase`
- `trajectory_summary`
  - `trend_label`
  - `largest_drop_turn_index`
  - `largest_gain_turn_index`

## Reglas de negocio

- cardinalidad de `trajectory[]` = turnos evaluables definidos por shaping.
- `direction` consistente con signo de `delta_vs_previous`.
- indexes válidos y únicos.

---

## 4) `ui_feedback_report_v1` (ensamblado backend)

## Propósito

Contrato estable para render de UI real.

## Estructura

- `schema_version: "ui_feedback_report.v1"`
- `header`
- `block_cards[]`
- `trajectory_chart`
- `key_moments`
- `recommendations_panel`
- `strengths_panel`
- `next_focus_panel`
- `closing_phrase_panel`
- `provenance`
  - `evaluation_id`
  - `bundle_hash`
  - `core_hash`
  - `trajectory_hash`
  - `core_model: gpt-5.4`
  - `trajectory_model: gpt-5.4`
  - `prompt_versions`
  - `schema_versions`

## Reglas

- la UI nunca consume directamente output crudo de runner.
- solo consume contrato ensamblado y validado.

---

## 5) Reconciliación core vs trajectory (normativa)

1. **Turnos inexistentes en core** → fallo duro (`failed`, `reconciliation_error.invalid_turn_reference`).
2. **Cardinalidad trajectory inválida** → si falta ≤10% y se puede rellenar seguro con `flat`+`unknown`, corrección segura; si no, fallo duro.
3. **Contradicción score global vs bloques**:
   - si desvío <= tolerancia: normalizar en ensamblador con marca `reconciled=true`.
   - si desvío > tolerancia: fallo duro.
4. **Outcome contradice facts derivados fuertes** (p.ej. acuerdo explícito en últimos turnos vs `blocked`): corrección segura solo si evidencia textual inequívoca; si no, fallo duro.
5. **Resumen de trayectoria contradice serie** (largest drop/gain inexistente): recomputar backend seguro y marcar reconciliación.

## Política de fallos

- fallo duro: no se publica reporte UI; job queda `failed` con artefactos.
- corrección segura: se corrige en ensamblador y se registra en `provenance.reconciliation_log`.

---

## 6) Qué calcula código vs LLM

- **Código**: shaping, facts derivados, validación, reconciliación, ensamblado, provenance.
- **LLM**: scoring cualitativo/cuantitativo en campos cerrados y reformulaciones.

Esta separación es obligatoria para mantener auditabilidad y evolución por versiones.
