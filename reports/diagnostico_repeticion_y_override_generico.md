# Diagnóstico: repetición de pregunta y override genérico en runtime

> Alcance: **solo diagnóstico**, sin fixes.

## Comandos usados
- `rg -n "Vale, dejémoslo así" -S .`
- `rg -n "asked_questions_recent|plan_ledger|retry_guard|attempts_for_key|active_key" backend -S`
- `rg -n "_block_.*retry|fallback_.*pivot|register_recent_question|extract.*question" backend -S`
- `nl -ba backend/negotiation/nodes/executor_node.py | sed -n '120,360p'`
- `nl -ba backend/negotiation/progress_updater.py | sed -n '1,420p'`
- `nl -ba backend/negotiation/nodes/progress_node.py | sed -n '1,140p'`
- `nl -ba backend/negotiation/negotiation_graph.py | sed -n '420,470p'`
- `nl -ba backend/negotiation/executor/render_executor.py | sed -n '320,420p'`
- `nl -ba backend/negotiation/elementos/render/executor_prompts.py | sed -n '53,92p'`
- `nl -ba backend/negotiation/llm_planning_context.py | sed -n '107,167p'`
- `nl -ba backend/negotiation/policy_progress.py | sed -n '53,95p'`

---

## 1) Mapa de archivos/funciones implicados

### A. Override por frase hardcodeada
- `backend/negotiation/nodes/executor_node.py`
  - `_fallback_pivot_question()` (string literal hardcodeado).
  - `_block_repeated_question_with_retry_guard(progress_state, executor_output)` (decide bloquear y reemplazar).
  - `executor_node(state)` (ordena render, validaciones y override final en `state`).

### B. Detección/registro de repetición
- `backend/negotiation/nodes/executor_node.py`
  - `_extract_question_text(response_text)` (extrae la **última** pregunta por split en `?`).
  - `_register_recent_question(progress_state, executor_output)` (persistencia en `plan_ledger.asked_questions_recent`).
- `backend/negotiation/progress_updater.py`
  - `_extract_question_text(text)` (misma lógica base: última pregunta por split en `?`).
  - `_record_recent_question(ledger, executor_output, last_assistant_message)`.
  - `_update_plan_ledger(...)` (llama `_record_recent_question`).
  - `update_progress_state(...)` (calcula `retry_guard`).

### C. Flujo de nodos (orden temporal)
- `backend/negotiation/negotiation_graph.py`:
  - `... -> phase_policy_planner -> progress_updater -> executor -> END`.
- `backend/negotiation/nodes/progress_node.py`:
  - `update_progress_state(...)` corre **antes** de `executor_node` en el turno.

### D. Prompt del executor
- `backend/negotiation/executor/render_executor.py`
  - `_build_retry_hint(state)`
  - `render_executor_output(...)` (construye prompt real y llama LLM).
- `backend/negotiation/elementos/render/executor_prompts.py`
  - `EXECUTOR_V2_USER_PROMPT` (incluye bloque `J) RETRY_HINT` textual).
- `backend/negotiation/llm_planning_context.py`
  - `build_executor_context_block_full(...)` (no inyecta plan_ledger/retry_guard como campos explícitos).

---

## 2) Condiciones exactas de activación

## A) Dónde/cuándo se reemplaza con la frase hardcodeada

### String y función
- String exacto: `"Vale, dejémoslo así. ¿Prefieres hablar ahora de documentación, precio o condiciones?"`.
- Origen: `_fallback_pivot_question()`.

### Condición booleana exacta de bloqueo
En `_block_repeated_question_with_retry_guard(...)`, el override solo ocurre si **todas** se cumplen:
1. `retry_guard.reached == True`
2. `executor_output.asked_question == True`
3. `_extract_question_text(executor_output.response_text) != ""`
4. `active_key_actual == retry_guard.active_key`
5. `question_text in plan_ledger.asked_questions_recent`

Si se cumplen, hace:
- `patched["response_text"] = _fallback_pivot_question()`
- `return normalize_executor_output(patched), True`

### Punto exacto de sobrescritura de estado
En `executor_node(...)`:
1. guarda salida LLM en `state["executor_output"]`, `state["assistant_message"]`, `state["response"]`.
2. corre validaciones/reparaciones.
3. llama `_block_repeated_question_with_retry_guard(...)`.
4. si `blocked_due_retry_guard`:
   - pisa `state["executor_output"]`
   - pisa `state["assistant_message"]`
   - pisa `state["response"]`

**Resultado:** LiveTrace puede mostrar `executor_llm.output_text_rendered` (texto original LLM) distinto del mensaje final al usuario, porque el override ocurre **después** de `record_llm_call(...)`.

## B) Orden real de pipeline (executor)
Orden observado en `executor_node`:
1. `render_executor_output(...)` (LLM)
2. `record_llm_call(...)`
3. set inicial de `executor_output/assistant_message/response`
4. `_register_recent_question(...)`
5. `validate_and_repair(...)` + enforcements
6. posible rewrite por validator/instruction/constraints
7. `_block_repeated_question_with_retry_guard(...)`
8. posible override hardcodeado final

---

## 3) Por qué permite repetición Turno 2 -> Turno 4 y luego override genérico

## A) La detección bloqueante depende de `retry_guard.reached`
El bloqueo en executor **no se evalúa por repetición sola**; exige `retry_guard.reached=True`.

`retry_guard.reached` se calcula en `update_progress_state(...)` como:
- `attempts_for_key = plan_ledger.attempt_counters_by_key[active_key]`
- `reached = attempts_for_key >= max_attempts`
- `max_attempts` viene de env `MAX_ATTEMPTS_PER_INTENT_STEP` (default `2`).

Y `attempt_counters_by_key[active_key]` solo incrementa cuando:
- `plan_status == "continue_same_step"` **y** `_judge_has_evidence(policy_plan_judgement)` retorna True.

`_judge_has_evidence(...)` exige:
- `policy_plan_judgement.evidence` sea lista no vacía
- y al menos un item dict con `quote` no vacío.

**Implicación diagnóstica:** se puede repetir pregunta en turnos intermedios aunque ya exista en `asked_questions_recent`, si todavía `reached=False` en ese turno.

## B) El registro de preguntas sí puede ocurrir antes
En executor se registra inmediatamente tras LLM (`_register_recent_question`).
En progress_updater también se puede registrar desde:
- `executor_output` del turno anterior, o
- fallback `last_assistant_message`.

Por tanto, la pregunta puede estar en ledger, pero el bloqueo no dispara hasta que además `retry_guard.reached` sea True y coincida `active_key`.

## C) Por qué aparece el override genérico “de repente”
Cuando en un turno posterior se acumulan intentos (`attempts_for_key >= max_attempts`) y el LLM vuelve a emitir una pregunta ya en `asked_questions_recent`, `_block_repeated_question_with_retry_guard` reemplaza el texto por la frase pivot fija.

---

## 4) Señales de estado que NO llegan explícitamente al prompt del executor

En `render_executor_output(...)` el prompt incluye:
- `executor_instruction_json`
- `advisor_recs_json`
- `world_json`
- `belief_json`
- `planner_output_summary` (`phase`, `policy_id`, `plan_id`)
- `retry_hint` (texto libre)

No se observan campos explícitos inyectados para:
- `plan_ledger.asked_questions_recent`
- `retry_guard.reached`
- `retry_guard.active_key`
- `retry_guard.attempts/max_attempts`
- `active_step_key` exacta (`plan_id:step_idx:intent_id`)

Diagnóstico: el executor recibe solo un hint textual (“NO repitas...”) pero no el estado estructurado mínimo para validar “esta pregunta ya está en dedupe del step activo”.

---

## 5) Sospecha de falsos positivos / inconsistencias de matching

## A) Matching de repetición es string exact match (sin normalización robusta)
La comparación bloqueante usa:
- `if question_text not in recent: return ...`

`question_text` se obtiene por `_extract_question_text(...)` y `recent` guarda strings crudos (con `strip`), sin:
- lowercase
- normalización de acentos
- normalización de signos/puntuación
- equivalencia semántica

**Consecuencia diagnóstica:**
- Más riesgo de **falsos negativos** (misma pregunta con variación mínima no coincide exacta).
- Posibles **falsos positivos** solo si dos preguntas distintas acaban colapsando al mismo `question_text` extraído.

## B) Extracción de pregunta potencialmente ambigua
La extracción en ambos módulos toma la **última** subsecuencia antes de `?`:
- `parts = text.split("?")`
- usa `parts[-1] + "?"`
- truncado a 180 chars.

Si el mensaje tiene varias preguntas o estructura mixta, puede terminar comparando una pregunta distinta de la “principal del step”.

## C) Riesgo de “contaminación” del ledger por fallback
En `progress_updater._record_recent_question(...)`, si no hay `executor_output.asked_question`, intenta extraer desde `last_assistant_message`.
Eso permite poblar `asked_questions_recent` con preguntas heredadas del último mensaje guardado, no necesariamente del intento actual del step.

---

## 6) Respuesta puntual a los objetivos solicitados

1. **Dónde/cuándo detecta repetición:**
   - Registro: en executor (mismo turno post-LLM) y en progress_updater (inicio del siguiente turno).
   - Bloqueo efectivo: solo en executor post-validaciones, condicionado por `retry_guard.reached` + matching exacto + `active_key`.

2. **Dónde/cuándo reemplaza por hardcode:**
   - `_fallback_pivot_question()` + `_block_repeated_question_with_retry_guard()` en executor.
   - Reemplazo ocurre al final de `executor_node`, después del `record_llm_call`.

3. **Por qué repite y luego override:**
   - Repite cuando aún no se alcanzó `retry_guard.reached` aunque ya haya duplicado en ledger.
   - Override aparece cuando luego sí se alcanza `reached` y la pregunta vuelve a coincidir exacta en `asked_questions_recent` para el mismo `active_key`.

4. **Señales faltantes en prompt executor (diagnóstico):**
   - No llegan explícitos `asked_questions_recent`, `retry_guard`, `active_key`, `attempts/max_attempts`.

5. **Falsos positivos/negativos en matching:**
   - Matching exacto + extracción de última pregunta + fallback por `last_assistant_message` => riesgo de desalineaciones (sobre todo falsos negativos y potencial comparación de pregunta no objetivo).
