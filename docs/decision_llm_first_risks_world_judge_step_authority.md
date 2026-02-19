# Decisión de diseño: riesgos críticos del flujo LLM-first

## Objetivo
Evaluar tres riesgos del flujo actual (`active_plan` + `executor_instruction` + `world judge` + `policy_progress`) y decidir **qué implementar ahora** vs **qué posponer**.

---

## 1) Riesgo: falta World Judge real antes de activar controlador

## Diagnóstico
**Severidad: ALTA**.

Estoy de acuerdo con el riesgo descrito:
- Si `POLICY_PLAN_JUDGE_ENABLED=1` y no existe judgement real por turno,
- `judgement_missing_streak` crecerá,
- se forzará `replan_policy`,
- y puede aparecer **replan churn** (replan recurrente por ausencia de señal, no por cambio real de contexto).

### Decisión
**Implementar YA un World Judge real en modo shadow** (no controlador todavía).

### Contrato mínimo recomendado (v1)
`policy_plan_judgement` (por turno):
- `plan_status` (enum obligatorio):
  - `completed`
  - `continue_same_step`
  - `advance_step`
  - `interrupted_replan`
- `why` (string corto, obligatorio)
- `evidence` (lista de citas; obligatoria para `completed/advance_step`)
- `confidence` (float 0..1)
- `degraded` (bool)
- `degrade_reason` (enum/string corto cuando corresponda)
- `plan_presence` (`active|none`)
- `evaluated_step_idx` (int cuando `plan_presence=active`)

### Reglas de degradación
- Si `plan_presence=none`:
  - emitir judgement explícito con `interrupted_replan` + `degraded=true` + `degrade_reason=no_active_plan`.
- Si `plan_status in {completed, advance_step}` y `evidence` vacía:
  - degradar a `continue_same_step` + `degraded=true` + `degrade_reason=missing_evidence_for_progress`.
- Si `confidence` baja (< umbral operativo):
  - mantener judgement pero marcar `degraded=true` + `degrade_reason=low_confidence`.

### Estrategia de despliegue
1. **Shadow** (ahora):
   - generar judgement siempre que world se ejecute;
   - solo logging/telemetría, sin gobernar `policy_progress`.
2. **Híbrido**:
   - judgement gobierna solo si `valid + evidence + confidence`.
   - fallback legacy en casos degradados/faltantes.
3. **Controlador**:
   - judgement como señal principal de transición.
   - fallback para incidentes/timeout.

---

## 3) Verificación de bugs equivalentes (kwargs duplicadas y sobrescrituras)

## Diagnóstico
**Severidad: MEDIA** (por impacto potencial, aunque sin evidencia concluyente actual de error activo).

### Método de verificación recomendado (sin comandos)
1. **Revisión estática de firmas y llamadas**
   - inspeccionar cada función crítica (`policy_progress_node`, `phase_policy_planner_node`, `world_updater_node`, `executor_node`):
   - comparar firma vs llamada para detectar kwargs duplicadas o inconsistentes.
2. **Revisión de asignaciones en scope**
   - buscar doble escritura de los mismos campos en el mismo flujo (`progress_state`, `policy_state`, `active_plan`, `executor_instruction`) para detectar sobrescritura silenciosa.
3. **Revisión de precedence de estado**
   - verificar orden de escritura/lectura por nodo:
   - quién escribe primero,
   - quién puede pisar después,
   - qué metadatos conservan trazabilidad del cambio.
4. **Pruebas de invariantes estructurales**
   - diseñar checks que aseguren unicidad semántica:
   - un único writer por campo crítico por nodo,
   - no degradar campos ya calculados sin razón explícita.
5. **Inspección de trazas de turnos consecutivos**
   - validar que valores intermedios no “reboten” por reasignación accidental.

### Decisión
**Implementar ahora un hardening de revisión/invariantes** (rápido, no invasivo) antes de ampliar controller.

---

## 4) Riesgo: desalineación de índices de step (`policy_state.step_idx` vs `active_plan.current_step_idx`)

## Diagnóstico
**Severidad: ALTA**.

Riesgo real en el flujo actual: existen dos relojes de progreso del step.
- `policy_progress` puede avanzar `policy_state.step_idx`.
- planner/world judge pueden avanzar `active_plan.current_step_idx`.

Esto puede crear estados incoherentes (avance doble, replan no sincronizado, executor leyendo step distinto al esperado por progress).

### Decisión
**Sí conviene unificar fuente de verdad ya a nivel de diseño**.

### Modelo de autoridad recomendado (single source of truth)
- **Fuente de verdad del step:** `active_plan.current_step_idx`.
- `policy_state.step_idx` pasa a compatibilidad transitoria (campo derivado/espejo), no autoritativo.
- `policy_progress` traduce judgement a control flow (`continue/replan/choose`) y, si mantiene `policy_state.step_idx`, debe sincronizarlo desde `active_plan` (no al revés).

### Transición incremental segura
1. **Etapa A (compatibilidad):**
   - `active_plan.current_step_idx` manda;
   - `policy_state.step_idx` se sincroniza como espejo.
2. **Etapa B (observabilidad):**
   - alertar divergencias `step_idx_mismatch` en trazas.
3. **Etapa C (simplificación):**
   - retirar lógica de avance autónomo de `policy_state.step_idx`.
4. **Etapa D (limpieza):**
   - conservar `policy_state.step_idx` solo si es necesario para back-compat externa.

---

## Plan integrado por etapas (recomendación final)

## Etapa 0 (inmediata)
- Activar trabajo de World Judge real en **shadow**.
- Añadir telemetría de divergencia de steps.
- Hardening de revisión de sobrescrituras/kwargs.

## Etapa 1 (híbrido controlado)
- `policy_progress` consume judgement solo si calidad mínima (`valid+confidence+evidence`).
- fallback legacy cuando judgement falta/degradado.

## Etapa 2 (controlador principal)
- judgement gobierna continuidad/avance/replan.
- step authority unificada en `active_plan.current_step_idx`.

---

## Señales de validación (trazas/tests) para evitar loops

1. `judgement_coverage_rate` (turnos con judgement válido).
2. `judgement_missing_streak_max` por sesión.
3. `replan_churn_rate` (replans consecutivos sin nueva evidencia).
4. `step_idx_mismatch_rate` (`policy_state` vs `active_plan`).
5. `phase_advance_rate_given_concession`.
6. `repeat_tone_policy_streak`.
7. `%advance_or_complete_with_evidence`.

### Criterio de éxito
- baja significativa de loops en climate,
- baja de replan churn,
- divergencia de step cercana a cero,
- mayor avance útil cuando hay concesiones explícitas.

---

## Decisión ejecutiva

- **Riesgo 1 (falta World Judge):** implementar ahora en shadow (**sí**).
- **Riesgo 3 (bugs equivalentes):** hardening ahora (**sí**, alcance acotado).
- **Riesgo 4 (doble step_idx):** unificar autoridad por diseño ya y transición incremental desde ahora (**sí**).

No recomiendo activar controlador full sin pasar por shadow+híbrido y sin resolver autoridad única de step.

## Nota operativa de flags (estado actual)

- Mantener `POLICY_PLAN_JUDGE_ENABLED=0` por defecto hasta tener World Judge real (aunque sea shadow robusto con contrato completo).
- `WORLD_JUDGE_NO_PLAN_AUTOFILL=1` puede usarse solo como soporte del caso `no_active_plan`; no sustituye judgement real de progreso.
