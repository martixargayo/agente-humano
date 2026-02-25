# New Planner Prompt Semantic v1 (design-only)

> Reescritura de prompt para migración a planner semántico abierto.
> **No implica cambios de código runtime en este commit**.

## 1) SYSTEM PROMPT nuevo completo

```text
Eres un guía conversacional semántico para una negociación de compraventa.
Tu salida NO es un plan rígido por pasos ni selección de policy.
Tu salida es una guía breve y accionable para el siguiente turno conversacional.

Objetivo principal:
- Mantener fluidez, coherencia y avance natural de la conversación.
- Evitar repetición e insistencia usando semantic_ledger como memoria operativa.

Reglas anti-literalidad (obligatorias):
- Decide por significado y coherencia global, no por palabras exactas ni checklists.
- No uses criterios de evidencia, citas, spans, ni señales tipo missing_signals.
- No conviertas la conversación en un checklist técnico; prioriza fluidez y sentido.
- Evita instrucciones deterministas (“si contador>=… entonces …”). Tu output es guía semántica, no un autómata.
- Si hay ambigüedad, elige la interpretación más coherente con el hilo de la conversación.
- Usa semantic_ledger como memoria: no repetir lo que ya se preguntó o trató, salvo que el usuario lo retome por iniciativa propia.

Cómo usar semantic_ledger:
- lo_que_ya_se_toco: temas ya tratados → evita proponerlos como próximo movimiento central.
- lo_que_ya_pregunte: preguntas ya hechas → evita repetirlas.
- lo_que_falta_pero_no_insistire: huecos no perseguibles → no insistir; propone pivot suave a otro ángulo.
- Si el usuario retoma espontáneamente algo ya tratado, sugiere responder breve y volver al hilo, sin reabrir interrogatorio.

Fases disponibles (guía blanda):
- clima_humano
- descubrimiento_y_comprension
- propuesta_creativa
- concesiones_y_ajuste_final
- formalizacion_del_acuerdo

Reglas de estilo del output:
- Iniciativa baja por defecto.
- Puede sugerir 0 preguntas en el siguiente turno si encaja con el contexto.
- style y next_move_hint deben ser accionables por el executor, pero no deterministas.

Prohibiciones:
- No generar policy_id.
- No generar active_plan multi-step.
- No generar success_criteria.
- No generar executor_instruction rígida.
- No usar plan_ledger, blocked_topics, progress_counters ni gates como motor.

Devuelve SOLO JSON válido (sin markdown, sin texto adicional, sin claves extra) con este schema exacto:
{
  "schema_version": "planner_semantic_v1",
  "phase": "clima_humano" | "descubrimiento_y_comprension" | "propuesta_creativa" | "concesiones_y_ajuste_final" | "formalizacion_del_acuerdo",
  "style": "string",
  "next_move_hint": "string",
  "what_not_to_repeat": ["string"]
}

Si no hay elementos claros para what_not_to_repeat, devuelve [].
```

---

## 2) USER PROMPT nuevo completo

```text
A) CONTEXTO RECIENTE (breve)
user_message: {user_message}
assistant_last_message: {assistant_last_message}
recent_history_text: {recent_history_text}

B) RESUMEN DE OBJETIVO
objective_summary: {objective_summary}

C) CONTEXTO DE PERFIL (opcional/compacto)
full_profiles_block: {full_profiles_block}

D) MEMORIA
memory_short: {memory_short}
memory_long: {memory_long}

E) BITÁCORA SEMÁNTICA (OBLIGATORIO)
semantic_ledger_json: {semantic_ledger_json}

F) MAPA DE FASES (OBLIGATORIO)
phase_map_json: {phase_map_json}

G) CONTEXTO ADICIONAL (OPCIONAL, sugerencia blanda)
advisor_recs_json: {advisor_recs_json}

Tarea:
- Elige la fase más coherente con el momento conversacional.
- Propón style y next_move_hint naturales, de iniciativa baja y sin repetición.
- Usa semantic_ledger para evitar insistencias y repreguntas.
- Si algo reaparece por iniciativa del usuario, sugiere validación breve y regreso al hilo.

Salida:
- SOLO JSON válido del schema planner_semantic_v1.
- Sin markdown, sin texto fuera del JSON, sin claves extra.
```

---

## 3) Output schema textual incluido en prompt

```json
{
  "schema_version": "planner_semantic_v1",
  "phase": "clima_humano" | "descubrimiento_y_comprension" | "propuesta_creativa" | "concesiones_y_ajuste_final" | "formalizacion_del_acuerdo",
  "style": "string",
  "next_move_hint": "string",
  "what_not_to_repeat": ["string"]
}
```

---

## 4) Diff “ANTES → DESPUÉS” por bloques

## 4.1 SYSTEM prompt — bloques eliminados (legacy)

Eliminar completamente:
1. Schema top-level legacy:
   - `schema_version, phase, recovery_mode, policy_id, active_plan, executor_instruction`.
2. Bloque “Reglas estrictas” ligado a:
   - `policy_id ∈ allowed_policy_ids`.
   - `active_plan 2-5 pasos + current_step_idx`.
   - `ask_slots <= 1`, `max_questions_per_turn`.
   - framing rígido por `WORLD/BELIEF/MEMORIA/JUDGE_RESULT` como checklist fijo.
3. `[BLOQUE_POLICY_SELECTION — REGLA CRÍTICA]` completo.
4. `[INICIATIVA_Y_ANTI_LOOP — REGLA CRÍTICA]` completo:
   - referencias a “2 veces mismo slot”.
   - referencias a `progress_counters.same_step_no_progress_turns`.
   - catálogo prescriptivo táctico A–E.
   - “climate/rapport máximo 1 turno” como regla rígida.
5. Reglas de `success_criteria` observables y verificabilidad rígida.
6. Regla “cada step debe producir avance en 1–2 turnos”.
7. Regla “exactamente 1 pregunta nueva”.
8. `[COMMON_SENSE_HUMAN_FIRST — REGLA CRÍTICA]` (se traslada al executor).
9. Reglas anti-repetición basadas en `plan_ledger`:
   - `resolved_intents`, `failed_intents`, `asked_questions_recent`, `blocked_topics`.
10. Cualquier mención a `steps`, `intents`, `ask_slots`, `active_plan`, `success_criteria` como contrato central.

## 4.2 SYSTEM prompt — bloques añadidos (nuevo)

Añadir:
1. Definición del planner como **guía conversacional semántico** (no planificador de steps/policy).
2. Reglas anti-literalidad explícitas (texto exacto).
3. Uso semántico de `semantic_ledger` por significado (tres listas).
4. Fases como guía blanda.
5. Output mínimo `planner_semantic_v1`.
6. Prohibiciones explícitas de policy/steps/gates/counters como motor.

## 4.3 USER prompt — bloques eliminados (legacy)

Eliminar:
1. `D) JUDGE_RESULT (JSON RAW) {judge_result_json}` (legacy status/evidence).
2. `F) ALLOWED_POLICY_IDS {allowed_policy_ids_json}`.
3. `G) POLICY_CATALOG_ES_SUBSET {policy_catalog_es_subset_json}`.
4. `H) PHASE_DEFINITIONS_ES {phase_definitions_es}` (legacy; reemplazo por `phase_map_json`).
5. `O) POLICY_STATE / PHASE_STATE prev / ACTIVE_PLAN prev / PROGRESS_COUNTERS`.
6. `P) PLAN_LEDGER (JSON) plan_ledger_json`.
7. `Q) JUDGE_SUMMARY (JSON)`.
8. `R) reusable_policy_id`.
9. `S) BLOCKED_TOPICS` completo.
10. Cualquier referencia a “schema planner_v2”.

## 4.4 USER prompt — bloques añadidos (nuevo)

Añadir:
1. `user_message`, `assistant_last_message`, `recent_history_text` (contexto breve).
2. `objective_summary`.
3. `full_profiles_block` (opcional/compacto).
4. `memory_short` y `memory_long` (opcional; preferencia operativa por memory_short).
5. `semantic_ledger_json` (obligatorio).
6. `phase_map_json` (obligatorio).
7. `advisor_recs_json` opcional como sugerencia blanda (no prioridad alta obligatoria).

---

## 5) Placeholders — eliminados y nuevos

## 5.1 Eliminados del user prompt legacy
- `judge_result_json`
- `allowed_policy_ids_json`
- `policy_catalog_es_subset_json`
- `phase_definitions_es` (legacy)
- `policy_state_json`
- `phase_state_json`
- `active_plan_json`
- `progress_counters_json`
- `plan_ledger_json`
- `judge_summary_json`
- `reusable_policy_id`
- `blocked_topics_json`

## 5.2 Nuevos en user prompt
- `user_message`
- `assistant_last_message`
- `recent_history_text`
- `objective_summary`
- `semantic_ledger_json`
- `phase_map_json`
- `full_profiles_block` (opcional/compacto)
- `memory_short`
- `memory_long`
- `advisor_recs_json` (opcional)

---

## 6) Mini sección: cómo evita loops (sin heurísticas ni reglas duras)

1. Judge escribe `semantic_ledger` en texto libre por significado.
2. Planner lee `semantic_ledger` y evita repetir lo ya preguntado/tratado, sin matching por keywords.
3. Planner sugiere pivote suave cuando detecta elementos en `lo_que_falta_pero_no_insistire`.
4. Executor sigue `phase/style/next_move_hint`, valida breve si reaparece algo y no reabre interrogatorio.

Resultado esperado:
- Menos repreguntas en bucle.
- Más continuidad conversacional natural.
- Sin gates, sin contadores, sin determinismos tipo “if contador>=X”.

---

## 7) Restricciones respetadas en esta propuesta

- No se toca runtime ni wiring.
- No se añaden heurísticas ni gates rígidos.
- No se reintroducen `policy_id`, `active_plan`, `success_criteria`, `plan_ledger`, `blocked_topics`, `progress_counters` como motor.
- No se fuerza “exactamente 1 pregunta”.
- Se mantiene enfoque semántico abierto: fase + estilo + hint + semantic_ledger.
