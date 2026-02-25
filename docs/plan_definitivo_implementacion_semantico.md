# PLAN DEFINITIVO — JUDGE SEMANTIC LEDGER → PROGRESS_STATE → PLANNER (SIN IDS, SIN HEURÍSTICAS)

## 1) Resumen ejecutivo

Este plan consolida la migración a un sistema semántico abierto donde el control rígido del flujo deja de depender de `plan_status`, evidence obligatoria, contadores de no-progreso y gates deterministas. El objetivo es priorizar coherencia conversacional real, reducir bucles por insistencia y mejorar naturalidad.

### Cambio de paradigma
- **Antes (legacy):** el judge actuaba como árbitro de progreso del plan (`continue/advance/interrupted/completed`), con reglas de evidencia y gates acoplados a contadores.
- **Ahora (definitivo):** el judge actúa como **scribe semántico**:
  - `topic_alignment` solo telemetría binaria (`on_topic|off_topic`),
  - actualización de `semantic_ledger` (texto libre),
  - sin control directo del flujo.

### Qué gana el sistema
- Menos literalidad forzada por reglas de evidencia/citas.
- Menos repreguntas de lo ya tratado.
- Planner guiado por memoria semántica acumulada, no por triggers rígidos.
- Executor con comportamiento más humano (no siempre “responder + preguntar”).

### Qué se abandona
- `plan_status` de 4 estados como motor.
- `skip_planner`, `missing_signals`, evidence/spans/citas obligatorias.
- Gates por `same_step_no_progress_turns`, `loop_flags`, `plan_id_changes_window`.
- Multi-step `active_plan` con `success_criteria` rígidos como núcleo de control.

---

## 2) Contratos definitivos (JSON shapes)

## 2.1 Judge: `judge_semantic_v1`

```json
{
  "schema_version": "judge_semantic_v1",
  "topic_alignment": "on_topic | off_topic",
  "reason_short": "string",
  "semantic_ledger": {
    "lo_que_ya_se_toco": ["string"],
    "lo_que_ya_pregunte": ["string"],
    "lo_que_falta_pero_no_insistire": ["string"]
  },
  "ledger_update_notes": "string"
}
```

Reglas semánticas de actualización (en prompt, no en gates de código):
- Frases cortas en español (aprox. 12–16 palabras por ítem).
- Dedupe por sentido (fusionar ideas equivalentes).
- Máx 6 ítems por lista (resumir si hace falta).
- Si hubo respuesta vaga a algo ya preguntado, reflejarlo en `lo_que_falta_pero_no_insistire`.

## 2.2 `progress_state` (ledger persistido)

```json
{
  "semantic_ledger": {
    "lo_que_ya_se_toco": ["string"],
    "lo_que_ya_pregunte": ["string"],
    "lo_que_falta_pero_no_insistire": ["string"]
  }
}
```

## 2.3 Planner output

```json
{
  "phase": "string",
  "style": "string",
  "next_move_hint": "string",
  "what_not_to_repeat": ["string"]
}
```

Notas:
- `what_not_to_repeat` puede ser opcional.
- El planner se guía por `semantic_ledger` para no insistir/repetir por semántica.

## 2.4 Executor (comportamiento esperado)
- Conversación natural, breve y contextual.
- No obligación de cerrar cada turno con pregunta.
- Si reaparece algo ya tratado, responder corto y no abrir seguimiento insistente.
- Mantener continuidad con fase/estilo y hint del planner.

---

## 3) Mapa de fases (con phase_id; sin topic IDs ni pools)

## Fase 1 — `clima_humano`
- **Qué hacer/cómo actuar:** cordialidad genuina, tono humano, cero presión.
- **Recomendaciones:** respuestas cálidas y breves; pregunta opcional y ligera.
- **Cuándo se usa:** inicio, tensión/fricción, o cuando la conversación va a lo personal.

## Fase 2 — `descubrimiento_y_comprension`
- **Qué hacer/cómo actuar:** comprender contexto/intereses sin sonar táctico.
- **Recomendaciones:** alternar responder, preguntar suave y responder+preguntar solo cuando aporte.
- **Cuándo se usa:** tras clima inicial y cuando falta contexto de decisión.

## Fase 3 — `propuesta_creativa`
- **Qué hacer/cómo actuar:** abrir opciones de cierre cuando hay bloqueo.
- **Recomendaciones:** plantear 1–2 alternativas claras y prácticas.
- **Cuándo se usa:** distancia en posiciones o estancamiento conversacional.

## Fase 4 — `concesiones_y_ajuste_final`
- **Qué hacer/cómo actuar:** ajuste fino con concesiones pequeñas y tono estable.
- **Recomendaciones:** pedir contrapartidas ligeras, mantener enfoque de cierre.
- **Cuándo se usa:** acuerdo base cercano, flecos pendientes.

## Fase 5 — `formalizacion_del_acuerdo`
- **Qué hacer/cómo actuar:** confirmar acuerdos de forma clara y tranquila.
- **Recomendaciones:** resumen corto de lo acordado y cierre confirmatorio.
- **Cuándo se usa:** cuando ambas partes ya muestran encaje.

---

## 3.1) Cómo funcionan los IDs de fase (`phase_id`)

- **Definición:** `phase_id` es un identificador estable de una fase conversacional (por ejemplo: `clima_humano`, `descubrimiento_y_comprension`).
- **Uso:** se usa para guía semántica, coherencia entre módulos (planner/executor/trazas) y lectura de observabilidad.
- **No-uso:** no es una lista de tareas deterministas, no es un catálogo de acciones obligatorias y no dispara gates automáticos.
- **Relación con “lo que se hace”:** los IDs aplican **solo a fases**. Las “cosas a hacer” se expresan en texto libre (`style`, `next_move_hint`), no como IDs.

**Ejemplo de planner output con `phase_id`:**

```json
{
  "phase": "descubrimiento_y_comprension",
  "style": "tono breve, humano y sin insistencia",
  "next_move_hint": "responder lo último y abrir un ángulo nuevo sin repetir",
  "what_not_to_repeat": ["no volver a pedir detalle técnico ya tratado"]
}
```

---

## 4) Wiring por módulo — BEFORE → AFTER

## 4.1 `backend/prompts.py`
- **Before:** prompts de judge/planner con control rígido (`plan_status`, evidence, steps/success_criteria).
- **After:**
  - Judge prompt -> `judge_semantic_v1` (telemetría + semantic ledger).
  - Planner prompt -> consume `semantic_ledger` y produce `phase/style/next_move_hint`.
- **Nuevos inputs clave:** `semantic_ledger_prev` (judge), `semantic_ledger` (planner).
- **Deja de usarse:** status/evidence/gates/counters como directrices de control.

## 4.2 `backend/negotiation/nodes/world_node.py`
- **Before:** payload judge con active_plan/step/success_criteria/progress_counters/evidence_candidates + normalización rígida.
- **After:** payload mínimo judge:
  - `user_message`
  - `assistant_last_message`
  - `recent_context`
  - `semantic_ledger_prev`
- **Output nuevo:** `judge_semantic_v1` en estado (contenedor telemétrico semántico).
- **Deja de usarse:** postprocesos de evidence/status coercion.

## 4.3 `backend/negotiation/progress_updater.py`
- **Before:** contadores/flags/ledger legacy para controlar replan/avance.
- **After:** persistencia de `semantic_ledger` desde output judge.
- **Output nuevo en estado:** `progress_state.semantic_ledger` actualizado.
- **Deja de usarse:** contadores legacy como motor decisional.

## 4.4 `backend/negotiation/phase_policy_planner.py`
- **Before:** planificaba con judge legacy + active_plan multi-step.
- **After:** planner recibe `semantic_ledger` y devuelve hint semántico por fase/estilo.
- **Input nuevo:** `semantic_ledger_json`.
- **Deja de usarse:** dependencia central de steps/success_criteria.

## 4.5 `backend/negotiation/nodes/planner_node.py`
- **Before:** gates por judge_status/skip_planner/no_progress + rutas de replan por contrato viejo.
- **After:** puente de contrato semántico planner→executor, sin gates rígidos legacy.
- **Input nuevo:** lectura de `progress_state.semantic_ledger` para planner call.
- **Deja de usarse:** decisiones por status/counters legacy.

## 4.6 `backend/negotiation/policy_progress.py` (+ node)
- **Before:** traducía `continue/advance/interrupted/completed` a `planner_request`.
- **After:** componente inocuo de sincronización mínima, sin control por status legacy.
- **Deja de usarse:** traducción de status como motor.

## 4.7 `backend/negotiation/nodes/executor_node.py` y/o `backend/negotiation/executor.py`
- **Before:** acoplado a instrucciones de step rígidas.
- **After:** consume `phase/style/next_move_hint` (y opcional `what_not_to_repeat`).
- **Comportamiento:** naturalidad; no insistir ni reabrir temas ya tratados.

## 4.8 `backend/negotiation/schemas.py`
- **Before:** estado priorizaba estructuras legacy de control.
- **After:** `semantic_ledger` como memoria principal para planner.
- **Compat:** campos legacy pueden permanecer temporalmente como inertes.

---

## 5) Lista EXACTA de eliminaciones/desactivaciones

## A) Judge prompt legacy (`backend/prompts.py`)
1. `WORLD_JUDGE_V2_SYSTEM_PROMPT` — bloque `plan_status` 4 estados → **eliminar**.
2. `WORLD_JUDGE_V2_SYSTEM_PROMPT` — evidence obligatoria/spans/citas → **eliminar**.
3. `WORLD_JUDGE_V2_SYSTEM_PROMPT` — `skip_planner` como regla → **eliminar**.
4. `WORLD_JUDGE_V2_SYSTEM_PROMPT` — `missing_signals` como control → **eliminar**.
5. `WORLD_JUDGE_V2_SYSTEM_PROMPT` — regla `same_step_no_progress_turns` → **eliminar**.
6. `WORLD_JUDGE_V2_USER_PROMPT` — `active_plan_json/current_step_json/success_criteria_json` → **eliminar**.
7. `WORLD_JUDGE_V2_USER_PROMPT` — `progress_counters_json/evidence_candidates_json` → **eliminar**.

## B) `world_node.py` evidence/status guardrails
1. `_normalize_judgement` (downgrade por evidence) → **eliminar**.
2. `_normalize_judgement` (forced interrupted por contador) → **eliminar**.
3. `_normalize_judgement` (coerción `skip_planner`) → **eliminar**.
4. `_post_normalize_evidence_guardrails` → **desactivar/eliminar** del camino crítico.
5. `_build_evidence_candidates` + helpers evidence → **fuera del camino crítico**.

## C) Gates/contadores legacy como motor
1. `same_step_no_progress_turns` / `no_progress_same_step_turns` → **desactivar como decisión**.
2. `loop_flags` → **desactivar como decisión**.
3. `plan_id_changes_window` → **desactivar como decisión**.
4. `plan_ledger` intent-based (resolved/failed/asked/blocked) como control → **desactivar**.

## D) Planner v2 multi-step
1. `active_plan` multi-step como contrato central → **eliminar**.
2. `success_criteria` como motor → **eliminar**.
3. regla “exactamente 1 pregunta nueva” → **eliminar**.
4. validaciones keyword-ish (`blocked_topics`, pivots asociados) como control → **eliminar/desactivar**.

## E) `policy_progress` status-translation
1. Traducción `continue/advance/interrupted/completed` a control → **desactivar**.

---

## 6) Prompts: qué se elimina y por qué se reemplaza

## 6.1 Judge (system+user)
### Eliminar del prompt legacy
- Toda lógica de control de plan (`plan_status`, `skip_planner`, evidence, missing_signals, counters).

### Reemplazar por
- Objetivo único: producir `judge_semantic_v1`.
- Entrada mínima: mensajes recientes + `semantic_ledger_prev`.
- Reglas de compactación/deduplicación por sentido.
- `topic_alignment` solo telemetría.

## 6.2 Planner
### Eliminar del prompt legacy
- Steps rígidos, success criteria, obligación de pregunta, señales de control por contadores.

### Reemplazar por
- Memoria central: `semantic_ledger_json`.
- Instrucción: no repetir lo ya tocado/preguntado.
- Si usuario trae tema previo: responder breve sin follow-up insistente.
- Output: `phase/style/next_move_hint` (+ opcional `what_not_to_repeat`).

## 6.3 Executor directrices
- Mantener naturalidad conversacional.
- No usar plantilla fija de pregunta por turno.
- Priorizar continuidad semántica con ledger y hint del planner.

---

## 7) Plan por etapas (sin código)

## Etapa 1 — Apagar legacy que bloquea semántica
- Sacar del camino crítico evidence/status/gates/counters.

## Etapa 2 — Prompts nuevos judge/planner/executor
- Introducir `judge_semantic_v1`.
- Introducir planner guiado por `semantic_ledger`.
- Ajustar directrices de executor a naturalidad/no-insistencia.

## Etapa 3 — Wiring semantic_ledger
- `world_node`: pasa `semantic_ledger_prev` al judge.
- `progress_updater`: persiste `semantic_ledger`.
- `phase_policy_planner`: consume `semantic_ledger` en prompt.

## Etapa 4 — Limpieza final legacy
- Dejar compat inerte temporal (campos legacy presentes sin control).
- Retirar rutas legacy activas cuando no haya consumidores.

## Etapa 5 — Test plan (diseño)
1. Judge contract test: shape exacta `judge_semantic_v1`.
2. Progress persistence test: guarda/actualiza `semantic_ledger`.
3. Planner input/output test: consume ledger y evita repetición por semántica.
4. Executor behavior test: respuesta breve sin reabrir temas ya tratados.
5. E2E trace test: reducción de loops e insistencia.

---

## 8) Riesgos + compat

### Qué puede romper
- Nodos/tests que esperan `plan_status`, `skip_planner`, `active_plan`, `planner_request` legacy.
- Dashboards/trazas que dependan de campos legacy específicos.

### Compat “relleno inerte” temporal (sin gates)
- Mantener campos legacy en estructura, pero sin usarlos para decidir flujo.
- Migrar consumidores al contrato nuevo antes de eliminar físicamente campos legacy.
- Retirar definitivamente campos legacy solo tras validación de consumidores.

---

## 9) Checklist final de aceptación

1. Judge ya no controla flujo; solo telemetría + ledger.
2. `semantic_ledger` persiste en `progress_state` y se actualiza turno a turno.
3. Planner consume `semantic_ledger` y reduce repetición semántica.
4. Executor no insiste en lo ya tratado y mantiene naturalidad.
5. Desaparecen del camino crítico:
   - `plan_status` 4 estados,
   - evidence/spans/citas obligatorias,
   - gates por no-progreso,
   - multi-step rígido con success criteria.
6. Trazas muestran menor churn y menos loops por repregunta.
