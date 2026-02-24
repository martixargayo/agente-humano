# Diagnóstico técnico: repetición / intentos infinitos en pipeline de negociación

## 1) Pipeline real y dependencias

### Orden real de nodos
En `negotiation_graph.py` el flujo es lineal y fijo:

1. `world_updater`
2. `belief_updater`
3. `policy_progress`
4. `phase_policy_planner`
5. `progress_updater`
6. `executor`

No hay bifurcación de grafo entre estos nodos; cada turno recorre toda la cadena.

### Paralelismo efectivo
Aunque el grafo es secuencial, `world_updater` lanza tareas paralelas internas (judge/advisor) y las deja pendientes; `policy_progress_node` llama explícitamente a `flush_world_parallel_pending(state)` para sincronizar esos resultados antes de derivar `planner_request`. Esto crea un punto de dependencia dura entre `world_updater` y `policy_progress`.

### Inputs relevantes a loops por nodo (visión ejecutiva)
- **world_updater**: plan activo + mensajes recientes + contexto; produce `policy_plan_judgement` (`plan_status`, `skip_planner`, etc.).
- **belief_updater**: depende de cambios de `world_state`; no decide retries, pero puede alterar señales de fase/riesgo.
- **policy_progress**: mapea `policy_plan_judgement.plan_status` a `policy_state.planner_request` y `progress_state.advance_step`.
- **phase_policy_planner**: ejecuta gate principal `continue/replan/advance`; puede saltarse planner LLM y reutilizar plan/policy.
- **progress_updater**: incrementa y persiste contadores (`no_progress_same_step_turns`, `policy_attempts`, `plan_id_changes_window`, `loop_flags`, ledger intentos).
- **executor**: genera respuesta final; registra preguntas recientes, pero hoy no bloquea de forma determinista repetición textual.

---

## 2) Contrato de datos actual por nodo (solo relevante)

## 2.1 `policy_progress_node` (`backend/negotiation/nodes/policy_progress_node.py`)

### Qué lee
- `state.policy_plan_judgement` (o fallback desde `world_state`)
- `state.progress_state.policy_state`
- `turn_count`, `world_state`, `belief_state`

### Qué computa
- `judgement_missing_streak`
- `last_judgement_status`
- Delega a `update_policy_state(...)` para decidir transición de policy.

### Qué escribe
- `progress_state.policy_state`
- `state.policy_hint`
- `state.policy_meta`
- `state.policy_plan_judgement` (normalizado de facto por presencia)

## 2.2 `update_policy_state` (`backend/negotiation/policy_progress.py`)

### Regla actual de transición
Según `plan_status`:
- `continue_same_step` → `planner_request = continue_policy` (o `replan_policy` si env var `PLANNER_FORCE_REPLAN_ON_CONTINUE_SAME_STEP=1`)
- `advance_step` → `planner_request = continue_policy` + `progress_state.advance_step=True`
- `completed` → `planner_request = replan_policy`
- `interrupted_replan`/otro → `planner_request = replan_policy`

### Implicación crítica
No usa `no_progress_same_step_turns`, `loop_flags` ni `attempt_counters` para forzar pivote. El control de retry está anclado al `plan_status` del judge + flag opcional por env.

## 2.3 `phase_policy_planner_node` (`backend/negotiation/nodes/planner_node.py`)

### Qué lee
- `progress_state.policy_state.planner_request`
- `progress_state.advance_step`
- `policy_plan_judgement.skip_planner`
- `progress_state.active_plan`

### Gate real reintentar vs replan
Si `planner_request == continue_policy` y hay plan previo:
1. **`advance_step=True`**: avanza índice local sin LLM (`advance_step_without_planner`), salvo último paso (entonces fuerza `replan_policy`).
2. **`judgement_skip_planner=True`**: reutiliza plan y salta planner (`judge_skip_planner`).
3. **Else continue**: clampa paso y, si existe `reusable_policy_id` permitido, salta planner (`continue_same_step_without_planner`); solo replanifica si no puede reutilizar policy.

Si no cumple lo anterior (p.ej. `planner_request=replan_policy`), llama a planner LLM y reconstruye plan.

### Qué escribe
- `progress_state.active_plan`, `active_plan_status`, `advance_step=False`
- `state.policy_decision`, `planner_meta`, `planner_debug`, `executor_instruction`
- Gate telemetry con razones de skip/ejecución

### Invariante frágil observada
`skip_planner` del judge tiene prioridad en ruta `continue_policy` y evita replan incluso si hay señales de loop en `progress_state` (porque no se consultan en gate).

## 2.4 `progress_updater_node` + `update_progress_state`

### `progress_updater_node` (`backend/negotiation/nodes/progress_node.py`)
- Llama a `update_progress_state(...)`.
- Marca como “frozen checks” que no deberían mutar aquí: `policy_plan_judgement`, `progress_state.active_plan`, `executor_instruction`, `progress_state.policy_state.planner_request`.
- Publica `progress_debug.anti_loop_signals` y cambios persistidos.

### `update_progress_state` (`backend/negotiation/progress_updater.py`)

#### Counters/flags principales
- `policy_attempts[policy_id] += 1` por turno con `policy_decision.policy_id`.
- `turns_in_same_mode` sube si repite `policy_id` elegido.
- `plan_id_changes_window` sube cuando cambia plan_id; decrece en caso contrario.
- `no_progress_same_step_turns` sube si `last_judgement_status == continue_same_step`, si no resetea a 0.
- `loop_flags`:
  - `continue_loop` si `no_progress_same_step_turns >= 3`
  - `replan_churn` si `plan_id_changes_window >= 2`
  - `stuck_in_policy` si `turns_in_same_mode>=2` y outcome no GOOD

#### Ledger por intent
`plan_ledger.attempt_counters[intent_id] += 1` cuando hay `policy_plan_judgement` + intent activo.
- Si status `continue_same_step` y attempts >=2, agrega `failed_intents`.
- Si `advance_step/completed`, agrega `resolved_intents`.
- Si `interrupted_replan`, agrega `failed_intents`.

### Punto clave
Estos indicadores se actualizan **después** del planner y executor del turno (nodo `progress_updater` va antes de `executor` en grafo, pero el estado de decisión de planner ya quedó fijado). Además, en el siguiente turno el planner no consume `loop_flags`/`attempt_counters` para bloquear retry.

## 2.5 `executor_node` (`backend/negotiation/nodes/executor_node.py`)

### Qué usa
- `policy_decision`, `executor_instruction`, `constraints_struct`, contexto de render.

### Retry hints / repetición
- Registra pregunta reciente en `plan_ledger.asked_questions_recent` (`_register_recent_question`).
- Enforcements actuales: `must_avoid`, max preguntas por turno, safe mode, compliance con instruction.

### Limitación
No existe chequeo determinista tipo “si pregunta igual a una de las últimas N y step/intent no cambió, bloquear/reescribir”. Por tanto puede repetir la misma pregunta aunque persista loop o incluso con plan_id distinto si la instrucción converge al mismo ask.

---

## 3) Lista de contadores/flags existentes (tabla)

| Campo exacto | Dónde se incrementa/actualiza | Cuándo se resetea | Quién lo consume hoy | Efecto actual |
|---|---|---|---|---|
| `progress_state.no_progress_same_step_turns` | `update_progress_state`: +1 si `last_judgement_status == continue_same_step` | a 0 si status distinto | Solo para `loop_flags` y debug | Señaliza loop; no fuerza replan por sí misma |
| `progress_state.loop_flags` (`continue_loop`, `replan_churn`, `stuck_in_policy`) | `update_progress_state` | Se eliminan cuando baja condición | `phase_state_updater` (recovery_mode por has_loop), debug | Impacta fase/recovery, no gate de planner retry |
| `progress_state.policy_attempts[policy_id]` | `update_progress_state` por turno con policy elegida | no reset explícito | `repair_policy_by_phase` bloquea candidatos con attempts>=3 | Solo afecta “phase repair”; no evita continue_same_step skip |
| `progress_state.plan_id_changes_window` | `update_progress_state` +1 al cambiar plan_id, -1 (hasta 0) si no | implícito por decremento | loop flag `replan_churn` | Telemetría/flag de churn |
| `progress_state.policy_state.planner_request` | `update_policy_state` desde `plan_status` | sobreescrito cada turno | `phase_policy_planner_node` | Controla si replan vs continue |
| `state.policy_plan_judgement.skip_planner` | world judge (`world_node`) | por salida de judge del turno | `phase_policy_planner_node` | Puede forzar saltar planner LLM |
| `progress_state.advance_step` | `update_policy_state` cuando `plan_status=advance_step` | planner lo pone False al final | `phase_policy_planner_node` | Avanza paso sin LLM |
| `progress_state.plan_ledger.attempt_counters[intent_id]` | `_update_plan_ledger` | no reset explícito global | Hoy no gatea planner/executor | Auditoría + base para failed_intents |
| `progress_state.plan_ledger.failed_intents[]` | `_update_plan_ledger` (continue>=2 o interrupted) | no reset explícito | validador de planes nuevos evita intents ya resueltos (no failed) | Registro histórico, sin hard stop |
| `progress_state.plan_ledger.asked_questions_recent[]` | executor + progress_updater | recorte a últimos 10 | hoy no usado para bloqueo determinista | Memoria de preguntas recientes |

---

## 4) Diagnóstico del motivo de “intentos infinitos”

## 4.1 Eslabón débil principal
**Los contadores anti-loop existen pero no están conectados al gate de decisión que evita reintentos.**

En concreto:
1. `policy_progress` puede seguir emitiendo `planner_request=continue_policy` para `continue_same_step`.
2. `phase_policy_planner_node` ante `continue_policy` tiende a **skip planner** y reutilizar plan/policy.
3. `update_progress_state` recién luego marca `continue_loop` (umbral 3) y aumenta `attempt_counters`.
4. En el turno siguiente, esos flags/counters no fuerzan pivot determinista en planner/executor.

## 4.2 Por qué repite preguntas (desglose solicitado)
- **¿El contador no sube?** Sí sube: `no_progress_same_step_turns`, `policy_attempts`, `attempt_counters` aumentan.
- **¿Sube pero no dispara nada?** Dispara `loop_flags`/`failed_intents`, pero mayormente observabilidad/recovery de fase.
- **¿Dispara pero planner lo ignora?** Sí: planner gate no consulta `loop_flags` ni `attempt_counters` para bloquear `continue_same_step_without_planner`.
- **¿Executor repite aunque cambie plan?** Posible: no hay hard dedupe por `asked_questions_recent`; sólo registro y límites de cantidad.

## 4.3 Regla dura anti-loop actual
No hay regla dura determinista de “máx 2 intentos por intent/step”.
- Umbral existente más cercano: `continue_loop` a los 3 `continue_same_step`, pero sin enforcement obligatorio.
- `repair_policy_by_phase` evita policies con `policy_attempts>=3`, pero eso solo aplica en fase de reparación de policy y no gobierna la ruta de skip planner en `continue_policy`.

## 4.4 Inconsistencias / invariantes rotos detectables
1. **Desacople temporal:** se decide continuar/reusar antes de actualizar contadores anti-loop del turno.
2. **Prioridad de `skip_planner`:** permite perpetuar continuidad sin considerar señales de loop acumuladas.
3. **Ledger incompleto para hard-stop:** `failed_intents` se registra, pero planner no evita explícitamente seguir en ese intent salvo que un plan nuevo lo cambie.
4. **Deduplicación de pregunta inexistente:** se almacena `asked_questions_recent` sin enforcement de no repetición.

---

## 5) Puntos de intervención recomendados (sin implementar)

Objetivo de diseño: **max_attempts=2 por intent/step; intento 3 => pivot obligatorio**.

### 1) `backend/negotiation/progress_updater.py` → `update_progress_state` / `_update_plan_ledger`
Agregar derivación canónica de intento por clave compuesta (`plan_id + step_idx + intent_id` o al menos `intent_id + step_idx`) y bandera explícita:
- `loop_flags += ["max_attempts_reached"]` cuando attempts > 2.
- Campo nuevo recomendado: `progress_state.retry_guard = { current_key, attempts, max_attempts, reached }`.

Compatibilidad legacy:
- Mantener `attempt_counters` actual; poblar nueva estructura en paralelo.
- Si falta plan/step, fallback a `intent_id` plano.

### 2) `backend/negotiation/policy_progress.py` → `update_policy_state`
Antes de fijar `planner_request`, leer `progress_state.retry_guard` y/o `plan_ledger.attempt_counters` del step/intent activo:
- Si `attempts >= 2` y judge vuelve `continue_same_step`, **forzar** `planner_request = replan_policy` y `meta.transition = force_planner`.
- Guardar reason machine-readable: `max_attempts_reached`.

### 3) `backend/negotiation/nodes/planner_node.py` → `phase_policy_planner_node`
En el gate de `continue_policy` añadir veto determinista:
- Si `max_attempts_reached` o loop flag equivalente del step activo => **prohibir** rutas `continue_same_step_without_planner` y `judge_skip_planner`; convertir a `replan_policy` (interrupted_replan path).
- Si planner_request continúa por legacy, aplicar override local igualmente (defensa en profundidad).

### 4) `backend/negotiation/nodes/world_node.py` (normalización de judgement)
Sin depender de LLM, endurecer normalización:
- Si llega `continue_same_step` con guardia excedida en estado, convertir judgement efectivo a `interrupted_replan` o marcar `degraded + force_replan`.
- Evita que salida del judge contradiga guardrail determinista.

### 5) `backend/negotiation/nodes/executor_node.py`
Aplicar dedupe determinista de pregunta:
- Si `asked_question=True` y la pregunta coincide con `asked_questions_recent` dentro de ventana + mismo step/intent, reescribir a pivot question (u opción A/B) y marcar meta (`question_dedup_applied`).
- Si guardia excedida, bloquear pregunta repetida y forzar prompt de transición.

### 6) `backend/negotiation/schemas.py` (opcional pero recomendable)
Formalizar nuevos campos en `ProgressState` (`retry_guard`, `max_attempts_per_intent_step`, `loop_flags` extendido) para evitar drift ad-hoc y facilitar migración/validación.

---

## 6) Plan de tests propuesto (sin codificar aún)

## 6.1 Unit tests de counters/guardrails
1. `update_progress_state`:
   - Caso `continue_same_step` x3 en mismo intent/step.
   - Assert: attempts 1→2→3, en 3 aparece `max_attempts_reached`.
2. `update_policy_state`:
   - Input judgement `continue_same_step` + guard reached.
   - Assert: `planner_request == replan_policy`.
3. `phase_policy_planner_node`:
   - Input `planner_request=continue_policy` + guard reached + plan activo + reusable policy.
   - Assert: no `continue_same_step_without_planner`; se ejecuta ruta replan.

## 6.2 Integration test de 4 turnos (1→2→3 pivota)
Escenario:
- Turno 1 y 2: judge retorna `continue_same_step`, misma señal insuficiente.
- Turno 3: aunque judge repita `continue_same_step`, guardrail debe forzar pivot.
- Turno 4: confirmar nuevo plan/intent o avance con baja confianza.

Asserts mínimos:
- `attempts` por step/intent = 1,2,3.
- En turno 3: `planner_request` forzado a replan/interrupted.
- `plan_id` o `intent_id` cambia (o `current_step_idx` avanza con marca explícita).
- `loop_flags` contiene `max_attempts_reached`.
- `executor_output.response_text` no repite `asked_question` exacta previa.

## 6.3 Regresión / compatibilidad
- Estados legacy sin nuevos campos deben seguir normalizando sin crash.
- `skip_planner=true` no debe derrotar guardrail cuando attempts excedidos.
- Con env `PLANNER_FORCE_REPLAN_ON_CONTINUE_SAME_STEP=1` comportamiento compatible (guardrail sigue dominando).

---

## Trace mental solicitado: caso loop de `continue_same_step` repetido 3 veces

Supuesto: mismo `plan_id`, mismo `step_idx`, misma pregunta casi idéntica.

### Turno T
1. `world_updater`: judge => `continue_same_step`, `skip_planner=false`.
2. `policy_progress`: pone `planner_request=continue_policy`.
3. `phase_policy_planner`: ve plan activo + policy reusable ⇒ **skip planner** (`continue_same_step_without_planner`), mantiene step.
4. `progress_updater`: incrementa `no_progress_same_step_turns` a 1; attempts intent=1.
5. `executor`: puede volver a preguntar algo similar.

### Turno T+1
Mismo patrón:
- Planner vuelve a skip.
- `no_progress_same_step_turns=2`; attempts intent=2; quizá `failed_intents` se actualiza.
- Sin pivot obligatorio.

### Turno T+2
Mismo patrón puede repetirse:
- Planner puede seguir en skip (siempre que reusable policy esté permitida).
- `no_progress_same_step_turns=3` activa `continue_loop`.
- **Pero** `continue_loop` no fuerza replan en gate actual, así que el loop puede persistir indefinidamente.

Conclusión operacional: el sistema detecta el loop, lo registra, pero no lo convierte en transición obligatoria del flujo.
