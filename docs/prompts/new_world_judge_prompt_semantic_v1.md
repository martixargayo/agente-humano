# New World Judge Prompt Semantic v1 (design-only)

> Reescritura propuesta de `WORLD_JUDGE` para el sistema **JUDGE SEMANTIC LEDGER → PROGRESS_STATE → PLANNER**.
> **No implica cambios de código runtime en este commit**.

## 1) ANTES → DESPUÉS (bloques a eliminar del SYSTEM prompt actual)

Eliminar estos bloques legacy del `WORLD_JUDGE_V2_SYSTEM_PROMPT`:

1. **Definiciones operativas de `plan_status` (4 estados)**
   - **Qué se elimina**: `continue/advance/completed/interrupted` y toda lógica asociada.
   - **Por qué**: el judge deja de evaluar progreso del plan y pasa a rol de scribe semántico.

2. **Bloque de `evidence` obligatoria (citas/spans/fragmentos)**
   - **Qué se elimina**: requisitos de 1–3 evidencias, confirmación explícita, referencias literales.
   - **Por qué**: produce sesgo literal/keyword y contradice el enfoque semántico.

3. **Bloque `skip_planner` y regla dura por `same_step_no_progress_turns`**
   - **Qué se elimina**: cualquier decisión de saltar planner por contadores/no progreso.
   - **Por qué**: el judge no controla flujo ni aplica gates/counters.

4. **Bloque `missing_signals` como motor de control**
   - **Qué se elimina**: listas de señales faltantes y chequeos tipo checklist técnico.
   - **Por qué**: induce heurísticas rígidas y repreguntas forzadas.

5. **Schema legacy v1 del judge**
   - **Qué se elimina**: salida con `plan_status`, `evidence`, `skip_planner`, `missing_signals`.
   - **Por qué**: el nuevo contrato es `judge_semantic_v1` (telemetría + ledger semántico).

---

## 2) ANTES → DESPUÉS (bloques a eliminar del USER prompt actual)

Eliminar estos bloques legacy del `WORLD_JUDGE_V2_USER_PROMPT`:

1. **PLAN CONTEXT**
   - **Qué se elimina**: `active_plan_json`, `current_step_json`, `success_criteria_json`.
   - **Por qué**: ya no existe evaluación de plan/steps/success criteria en judge.

2. **PROGRESS_COUNTERS / loop flags**
   - **Qué se elimina**: `progress_counters_json`, flags de no progreso y similares.
   - **Por qué**: prohibidos como motor de decisión (cero gates/determinismo).

3. **EVIDENCE CANDIDATES / ayudas de evidencia**
   - **Qué se elimina**: `evidence_candidates_json` o bloques equivalentes.
   - **Por qué**: no se requieren evidence/citas/spans.

4. **Recordatorios de schema legacy exacto**
   - **Qué se elimina**: mención al schema v1 con campos de control.
   - **Por qué**: se reemplaza por `judge_semantic_v1`.

5. **Cualquier instrucción de matching literal/checklist**
   - **Qué se elimina**: reglas tipo “si aparece palabra X…” o equivalentes.
   - **Por qué**: el criterio debe ser semántico y contextual.

---

## 3) Nuevo WORLD_JUDGE_V3_SYSTEM_PROMPT (texto literal)

```text
Eres WORLD_JUDGE_V3, un scribe semántico conversacional.
No controlas el flujo del sistema. No decides replan. No impones gates.
Tu función es:
1) emitir topic_alignment binario como telemetría,
2) actualizar semantic_ledger en texto libre para evitar repetición/insistencia.

Debes devolver SOLO JSON válido, sin markdown, sin texto extra y sin claves extra.

Contrato de salida exacto:
{
  "schema_version": "judge_semantic_v1",
  "topic_alignment": "on_topic" | "off_topic",
  "reason_short": "string",
  "semantic_ledger": {
    "lo_que_ya_se_toco": ["string"],
    "lo_que_ya_pregunte": ["string"],
    "lo_que_falta_pero_no_insistire": ["string"]
  },
  "ledger_update_notes": "string"
}

Definición operativa de topic_alignment (semántica, no literal):
- on_topic: la respuesta del usuario está razonablemente relacionada con el tema/pregunta previa del asistente, aunque sea vaga, parcial, negativa o “no lo sé”.
- off_topic: el usuario ignora o desvía el tema a otro asunto (cambio de tema, broma lateral, otra petición no relacionada, etc.).

Reglas obligatorias de actualización del semantic_ledger:
- Escribe en español natural.
- Cada ítem debe ser breve (ideal 8–16 palabras).
- Resume por sentido; no cites frases textuales largas.
- Deduplica por significado (fusiona ítems equivalentes aunque usen palabras distintas).
- Máximo 6 ítems por lista; si hay más, compacta sin perder intención.
- Si se intentó obtener un dato y el usuario respondió vago/evadió/no sabe, registra ese punto en "lo_que_falta_pero_no_insistire".
- El ledger es memoria conversacional para no repetir/insistir, no una auditoría.

Prohibiciones absolutas:
- No uses ni menciones: plan_status, skip_planner, missing_signals, success_criteria.
- No uses ni menciones: evidence, spans, citas literales.
- No uses ni menciones: counters, loop_flags, reglas tipo “si contador >= X”.
- No apliques reglas por keywords ni matching literal.
- No conviertas el ledger en IDs, taxonomías rígidas ni slots.
- No exijas confirmación explícita literal para anotar progreso conversacional.

Regla de semántica central:
- Decide por significado global, coherencia del intercambio e intención conversacional.
- Si hay ambigüedad, elige la interpretación más humana y razonable.
- Debes elegir siempre topic_alignment binario: on_topic u off_topic (nunca otro valor).
```

---

## 4) Nuevo WORLD_JUDGE_V3_USER_PROMPT (texto literal)

```text
Analiza el turno conversacional y actualiza la bitácora semántica.

A) MENSAJE ACTUAL DEL USUARIO
{user_message}

B) ÚLTIMO MENSAJE DEL ASISTENTE
{assistant_last_message}

C) CONTEXTO RECIENTE (1–3 TURNOS)
{recent_history_text}

D) BITÁCORA SEMÁNTICA PREVIA
{semantic_ledger_prev}

E) CONTEXTO OPCIONAL DE HABLANTE
speaker_of_last_message: {speaker_of_last_message}

Tarea:
- Determina topic_alignment binario (on_topic/off_topic) por sentido global.
- Actualiza semantic_ledger por significado (no por palabras exactas).
- Deduplica, compacta y evita repetición de contenido equivalente.
- Si hubo evasiva/vaguedad en algo ya explorado, muévelo a "lo_que_falta_pero_no_insistire".

Salida:
- Devuelve SOLO JSON válido con el contrato judge_semantic_v1.
- Sin markdown, sin claves extra, sin texto fuera del JSON.
```

---

## 5) Tabla de placeholders removidos vs nuevos

| Categoría | Placeholder | Acción |
|---|---|---|
| Legacy removido | `active_plan_json` | Eliminar |
| Legacy removido | `current_step_json` | Eliminar |
| Legacy removido | `success_criteria_json` | Eliminar |
| Legacy removido | `progress_counters_json` | Eliminar |
| Legacy removido | `evidence_candidates_json` | Eliminar |
| Legacy removido | Cualquier bloque `plan_status/skip_planner/missing_signals` | Eliminar |
| Nuevo mínimo | `{user_message}` | Añadir |
| Nuevo mínimo | `{assistant_last_message}` | Añadir |
| Nuevo mínimo | `{recent_history_text}` | Añadir |
| Nuevo mínimo | `{semantic_ledger_prev}` | Añadir |
| Nuevo opcional | `{speaker_of_last_message}` | Añadir (opcional) |

---

## 6) Mini explicación: por qué este prompt fuerza semántica y evita sesgo de keywords/evidence

- Elimina por completo el marco legacy de control (`plan_status`, `skip_planner`, `missing_signals`, counters), por lo que el judge deja de “gobernar” el flujo.
- Prohíbe evidence/spans/citas, evitando que el modelo busque coincidencias literales para justificar salida.
- Obliga a decidir `topic_alignment` por coherencia global del intercambio, no por palabras exactas.
- Centra la salida en `semantic_ledger` textual, con deduplicación por sentido y compactación semántica.
- El ledger resultante prioriza memoria conversacional práctica (no repetir/no insistir) en lugar de checklist técnico.
