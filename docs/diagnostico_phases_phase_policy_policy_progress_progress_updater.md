# Diseño definitivo — `phase_policy_planner` LLM-first
## Spec operativa (sin código) para planificación multi-turn + handoff instruccional (Opción B)

> Este documento define el comportamiento final deseado del nuevo `phase_policy_planner` bajo filosofía LLM-first con contrato estricto.

---

## 0) Resumen de arquitectura y roles

### Pipeline (sin cambios de orden)

```text
world_updater
  -> belief_updater
  -> policy_progress
  -> phase_policy_planner
  -> executor
```

### Autoridad de decisión

- **World Judge (en world_updater, cuando aplique)**: juzga el resultado del step anterior y emite `policy_plan_judgement`.
- **policy_progress**: orquesta flujo (`continuar`, `avanzar`, `replanificar`) según judgement; no hace análisis semántico profundo.
- **phase_policy_planner**: autoridad principal para diseñar el plan (fase + inspirations + steps).
- **executor (Opción B)**: ejecuta instrucción natural del step activo; no ejecuta “policy literal”.

---

## 1) Inputs exactos que recibe el planner

El planner debe recibir **siempre** estos bloques en el prompt de entrada:

1. `world_state` (resumen + campos clave)
2. `belief_state`
3. `active_plan` actual (objeto completo) **o** `none`
4. `policy_plan_judgement` del turno anterior **o** `none`
5. `agent_objective` (rol/intención/constraints)
6. `recent_history` breve (últimos N turnos)

## 1.1 Estructura recomendada por bloque

### `world_state` (mínimo útil)
- Señales de negociación actuales (precio, deadline, concesiones, ofertas, open points).
- Señales de interacción (tono, fricción, escalada, loop hint).
- Señales estructurales (`negotiation_v2` o equivalente operacional).

### `belief_state`
- Estimación de salud de interacción (`stable/tense/stalled`).
- Riesgo de conflicto.
- Hipótesis activas con confianza.

### `active_plan`
- Plan persistido del ciclo previo o `none`.
- Incluye `plan_id`, `current_step_idx`, `steps`, `horizon_turns`.

### `policy_plan_judgement`
Enum cerrado:
- `completed`
- `continue_same_step`
- `advance_step`
- `interrupted_replan`

Con:
- `why`
- `evidence` (citas)
- `confidence`

### `agent_objective`
- Qué intenta lograr el agente a nivel de producto (acuerdo viable, claridad, seguridad, etc.).
- Restricciones duras (seguridad, límites de tono, límites de preguntas, no inventar hechos).

### `recent_history`
- Resumen corto de 3–6 turnos.
- Debe conservar cambios de contexto y compromisos recientes.

## 1.2 Ejemplo de input realista A (concesión condicional)

```json
{
  "world_state": {
    "signals": {"price_mentioned": false, "deadline_claimed": false},
    "world_buckets": {"concessions": ["si me pagas más hoy, yo te pago la ITV 2 años"]},
    "negotiation_v2": {"offers": [], "interests": [], "agreement_state": {"state": "none", "confidence": 0.0}}
  },
  "belief_state": {
    "interaction_health": "stable",
    "conflict_risk": 0.24,
    "hypotheses": ["interés en liquidez inmediata"]
  },
  "active_plan": "none",
  "policy_plan_judgement": "none",
  "agent_objective": {
    "goal": "avanzar hacia acuerdo verificable sin escalar",
    "constraints": ["no inventar", "máx 2 preguntas", "tono colaborativo"]
  },
  "recent_history": ["usuario ofrece concesión condicional ligada a pago hoy"]
}
```

## 1.3 Ejemplo de input realista B (con plan activo y judgement)

```json
{
  "world_state": {
    "signals": {"price_mentioned": true, "deadline_claimed": true},
    "negotiation_v2": {"offers": [{"kind": "claim", "value": "9500"}], "interests": ["cerrar hoy"]}
  },
  "belief_state": {
    "interaction_health": "stable",
    "conflict_risk": 0.32
  },
  "active_plan": {
    "plan_id": "plan_price_03",
    "current_step_idx": 0,
    "horizon_turns": 3,
    "steps": [{"step_idx": 0, "micro_goal": "verificar credibilidad de oferta externa"}]
  },
  "policy_plan_judgement": {
    "plan_status": "continue_same_step",
    "why": "faltó evidencia verificable",
    "evidence": [{"quote": "me lo dijeron por teléfono"}],
    "confidence": 0.82
  },
  "agent_objective": {
    "goal": "verificar presión temporal y estructurar propuesta",
    "constraints": ["no ceder sin datos", "tono neutro"]
  },
  "recent_history": ["usuario mantiene claim de oferta y deadline"]
}
```

---

## 2) Decisión de fase (sin rigidez)

> La fase es **brújula** de estilo y objetivo, NO cortafuegos rígido de repertorio.

Fases propuestas:

## 2.1 `climate`
- **Objetivo típico**: estabilizar canal comunicativo, reducir fricción.
- **Señales de entrada**: tensión, ambigüedad alta, baja cooperación.
- **Señales de salida**: tono estable + intención de avanzar + claridad mínima.
- **Errores a evitar**: quedarse indefinidamente en validación emocional cuando ya hay concesiones concretas.

## 2.2 `interests`
- **Objetivo típico**: descubrir motivaciones, límites y valor real para ambas partes.
- **Señales de entrada**: concesiones condicionales, mención de prioridades, urgencias.
- **Señales de salida**: intereses/criterios suficientemente claros para diseñar opciones.
- **Errores a evitar**: pedir datos irrelevantes y no convertir señales en criterios operativos.

## 2.3 `options`
- **Objetivo típico**: generar 1–3 paquetes de intercambio.
- **Señales de entrada**: ya hay criterios/intereses suficientes.
- **Señales de salida**: aparece una opción preferida con viabilidad.
- **Errores a evitar**: proponer opciones sin anclarse a restricciones reales.

## 2.4 `adjust`
- **Objetivo típico**: negociar trade-offs y cerrar brechas.
- **Señales de entrada**: anclas de precio, deadline, objeciones concretas.
- **Señales de salida**: convergencia clara o condiciones casi cerradas.
- **Errores a evitar**: escalar presión sin evidencia ni reciprocidad.

## 2.5 `formalize`
- **Objetivo típico**: confirmar términos, siguientes pasos y condiciones.
- **Señales de entrada**: acuerdo cercano / puntos abiertos mínimos.
- **Señales de salida**: confirmación explícita o decisión de no cierre.
- **Errores a evitar**: cerrar sin verificar términos operativos.

---

## 3) Repertorio de policies (~15) como inspirations

> El catálogo completo y mantenible vive en un documento separado:
> **`docs/planner_policy_repertoire_v1.md`**

Aquí se usa un repertorio reducido (~15) como patrones:

1. `safe_neutral_core`
2. `deescalate_tension`
3. `boundary_and_respect`
4. `clarify_missing_info`
5. `info_extract_critical`
6. `discover_interests_open`
7. `time_pressure_probe`
8. `credibility_probe`
9. `tradeoff_if_then`
10. `package_option_builder`
11. `objection_handler`
12. `anchor_reframe_soft`
13. `micro_commitment_next_step`
14. `formalize_recap_confirm`
15. `close_graciously`

## 3.1 Regla de uso del planner

- Selecciona 1–3 `inspirations` por turno con `fit_reason`.
- Diseña el plan libremente apoyándose en ellas.
- No copia texto ni ejecuta plantilla rígida de policy.
- Si contexto cambia fuerte, puede cambiar inspirations con justificación.

---

## 4) Cómo crea el plan multi-turn (algoritmo mental)

## 4.1 Pasos del planner

1. **Leer world/belief** para entender estado negociador y salud interactiva.
2. **Leer judgement anterior** (`policy_plan_judgement`) para saber qué pasó en el step previo.
3. **Inferir fase actual** como guía de intención y estilo.
4. **Elegir inspirations (1–3)** según fit semántico.
5. **Generar plan 1–4 steps** con, por step:
   - `micro_goal`
   - `what_to_do`
   - `ask` (0–2 preguntas)
   - `success_criteria`
   - `replan_triggers`
   - `safe_mode`
6. **Emitir `executor_instruction`** del step activo.

## 4.2 Escenario 1 — Concesión condicional ITV

**Input usuario**: “si me pagas más hoy, yo te pago la ITV 2 años”

**Output resumido esperado**:
- `phase_assessment.phase = interests` (o `options` con conf media-alta).
- inspirations: `info_extract_critical`, `tradeoff_if_then`.
- plan:
  1) concretar alcance/condiciones ITV,
  2) cuantificar valor y contrapartida,
  3) validar viabilidad de paquete.
- `executor_instruction`: pregunta concreta y verificable sobre alcance/coste.

## 4.3 Escenario 2 — Tensión/amenaza (recovery)

**Input usuario**: amenaza / insulto.

**Output resumido esperado**:
- `phase_assessment.phase = climate`, `recovery_mode=true`.
- inspirations: `deescalate_tension`, `boundary_and_respect`.
- plan corto (1–2 steps) de contención.
- `executor_instruction.safe_mode = deescalate|boundary`.

## 4.4 Escenario 3 — Precio + deadline

**Input usuario**: “tengo oferta de 9.500 y cierro hoy”

**Output resumido esperado**:
- fase guía: `adjust` (o `interests` si falta verificación).
- inspirations: `time_pressure_probe`, `credibility_probe`, `tradeoff_if_then`.
- plan 2–3 steps:
  1) verificar oferta/plazo,
  2) construir paquete condicional,
  3) preparar cierre operativo.
- `executor_instruction`: solicitar evidencia concreta + términos.

---

## 5) Contratos JSON v1 (obligatorio)

## 5.1 `active_plan` (persistido)

```json
{
  "active_plan_status": "none | active | completed | interrupted",
  "active_plan": {
    "schema_version": "v1",
    "plan_id": "string<=40",
    "created_turn": 0,
    "updated_turn": 0,
    "horizon_turns": 1,
    "current_step_idx": 0,
    "phase_assessment": {
      "phase": "climate | interests | options | adjust | formalize",
      "confidence": 0.0,
      "reason": "string<=180",
      "evidence": [
        {"quote": "string<=180", "source": "user_message | world | belief"}
      ],
      "recovery_mode": false
    },
    "inspirations": [
      {"policy_id": "string<=60", "fit_reason": "string<=120", "risk": "low | mid | high"}
    ],
    "global_goal": "string<=180",
    "steps": [
      {
        "step_idx": 0,
        "micro_goal": "string<=160",
        "what_to_do": "string<=260",
        "ask": ["string<=140"],
        "success_criteria": ["string<=120"],
        "replan_triggers": ["string<=80"],
        "safe_mode": "normal | deescalate | boundary"
      }
    ],
    "plan_constraints": {
      "max_questions_per_turn": 2,
      "must_avoid": ["string<=90"],
      "stop_conditions": ["string<=90"]
    }
  }
}
```

### Reglas mínimas
- `active_plan_status="none"` => `active_plan=null`.
- `horizon_turns` en [1,4].
- `steps` en [1,4].
- `current_step_idx` válido.
- `ask` por step en [0,2].

## 5.2 `phase_assessment` (sub-bloque obligatorio)

```json
{
  "phase": "climate | interests | options | adjust | formalize",
  "confidence": 0.0,
  "reason": "string<=180",
  "evidence": [{"quote": "string<=180", "source": "user_message | world | belief"}],
  "recovery_mode": false
}
```

### Regla de validación clave
- Si `confidence >= 0.65`, `evidence` no debe estar vacía.

## 5.3 `executor_instruction` (handoff a executor)

```json
{
  "executor_instruction": {
    "schema_version": "v1",
    "plan_id": "string<=40",
    "step_idx": 0,
    "step_micro_goal": "string<=160",
    "instruction": "string<=320",
    "ask": ["string<=140"],
    "safe_mode": "normal | deescalate | boundary",
    "must_follow": ["string<=90"],
    "must_avoid": ["string<=90"],
    "stop_conditions": ["string<=90"],
    "trace_tags": ["string<=60"]
  }
}
```

### Reglas mínimas
- `instruction` obligatorio.
- `safe_mode` obligatorio.
- `ask` máximo 2.
- `must_avoid` y `stop_conditions` obligatorias cuando `safe_mode != normal`.

---

## 6) Reglas de continuidad vs replanteo (tabla de decisión)

| `policy_plan_judgement.plan_status` | Comportamiento esperado del planner |
|---|---|
| `continue_same_step` | Mantener plan y step; refinar `what_to_do`/`ask` sin reescribir todo. |
| `advance_step` | Avanzar `current_step_idx`; mantener plan_id; actualizar instruction del nuevo step. |
| `completed` | Cerrar plan actual (`active_plan_status=completed`) y crear plan nuevo solo si aún hay objetivo abierto. |
| `interrupted_replan` | Crear plan nuevo (`new plan_id`) explicando motivo de replanteo. |

## Regla adicional cuando falta judgement

- Si `policy_plan_judgement = none`:
  - con `active_plan=active`: continuar 1 turno con mínima variación y registrar `judgement_missing_streak`.
  - si streak>=2: replan breve por seguridad operativa.
  - con `active_plan=none`: planificar de cero.

---

## 7) Guardrails mínimos (sin matar libertad)

### Se mantiene duro

1. JSON válido y validable.
2. `safe_mode` por step.
3. máximo de preguntas por turno (`<=2`).
4. `must_avoid` / `stop_conditions`.
5. en `recovery_mode`: restricciones estrictas de tono/contenido.

### Se evita explícitamente

- gating rígido por fase tipo “allowed_policy_ids por fase” como muro duro.
- dependencia de policy literal para ejecutar.
- sobrecarga de heurísticas semánticas en `policy_progress`.

---

## 8) Telemetría mínima para debug

Loggear siempre:

1. `phase_assessment.phase` + `confidence` + `evidence`.
2. inspirations elegidas + `fit_reason`.
3. `plan_diff` (si cambió plan o solo step/instruction).
4. `replan_reason` (si hubo replanteo).
5. `judgement_missing_streak`.
6. `authority_resolution` (qué componente prevaleció si hubo conflicto).

---

## 9) Checklist “esto está bien / esto está mal”

## Bien
- Plan coherente con `plan_id` estable entre pasos.
- Cambios pequeños cuando judgement dice `continue_same_step`.
- Replan justificado cuando judgement dice `interrupted_replan`.
- Executor recibe instrucción clara, segura y accionable.
- Evidencia explícita en fase y juicios de avance.

## Mal
- Cambiar de plan cada turno sin motivo.
- Repetir deescalación cuando ya hay concesión concreta sin intentar estructurarla.
- Step sin `success_criteria` o sin `safe_mode`.
- `completed/advance_step` sin evidencia.
- Policy_progress “pensando semántica” en lugar de orquestar.

---

## 10) Recomendación final de MVP (activar primero)

### MVP rápido en 2 fases

1. **Fase MVP-1**
   - planner genera `active_plan` + `executor_instruction` (Opción B)
   - executor consume instruction del step activo
   - policy_progress sigue casi igual (orquestación mínima)

2. **Fase MVP-2 (shadow de World Judge)**
   - world emite `policy_plan_judgement` en logging
   - no gobierna flujo aún
   - medir divergencia con decisiones reales

3. **Fase MVP-3 (híbrido controlado)**
   - judgement válido y robusto empieza a gobernar continuidad/avance/replan
   - fallback legacy cuando judgement falta por gating o baja confianza

### Criterio de éxito inicial
- ↓ loops en climate con concesiones explícitas.
- ↓ repetición de movimientos de tono sin avance.
- ↑ coherencia step-to-step en executor.

---

## 11) Documento de policies (ubicación oficial)

El repertorio reducido y su definición operacional deben mantenerse en:

- **`docs/planner_policy_repertoire_v1.md`**

Este documento principal referencia ese repertorio, pero no lo sustituye.
