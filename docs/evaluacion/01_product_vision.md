# 01 — Product vision

## UX objetivo end-to-end

### 1) Estado conversacional normal

El usuario negocia en la UI actual. El backend devuelve `finish_button_armed` según fase (`formalizacion_del_acuerdo` o `abandono_de_la_negociacion`).

### 2) Acción de cierre

Al pulsar **Finalizar conversación**:

- abrir modal de confirmación,
- mostrar impacto: “se cerrará la conversación y se generará informe de desempeño”,
- CTA principal: “Sí, finalizar y evaluar”.

### 3) Creación de evaluación

Tras confirmar:

- frontend llama `POST /api/interfaz_usuario/feedback/evaluations` (nuevo),
- recibe `evaluation_id` + `status=created|queued`,
- navega a pantalla de loading.

### 4) Pantalla de loading

Comportamiento:

- polling cada 1.5–2s a `GET /api/interfaz_usuario/feedback/evaluations/{evaluation_id}`,
- barra/estado textual según fase del job,
- timeout de UX (p.ej. 90s) con fallback amable si tarda más.

### 5) Pantalla informe

Cuando `status=completed`:

- frontend consume `ui_feedback_report_v1`,
- renderiza bloques visuales sin postproceso semántico libre,
- muestra acciones sugeridas y navegación por turnos.

---

## Especificación funcional de la pantalla de informe

## A. Cabecera

Datos requeridos:

- `report_title` (fijo: Informe de desempeño),
- `activity_name` (negociación),
- `duration_seconds` + `duration_human`,
- `generated_at_utc`,
- `stars` (0–5 con paso configurable),
- `score_global_100`,
- `interaction_outcome` (`agreement_reached`, `partial_progress`, `no_agreement`, `blocked`),
- `summary_2_3_lines`.

## B. 4 bloques principales

Para negociación v1:

1. comprensión y exploración,
2. comunicación y clima,
3. movimiento táctico,
4. cierre y avance.

Cada bloque requiere:

- `block_id`, `title`, `status_visual` (`correcto|mejorable|mal`),
- `score_0_100`,
- `checks[]` con `polarity` (`check|cross`) + microexplicación,
- `block_verdict`.

## C. Trayectoria turno a turno

El gráfico usa una métrica **cercanía a acuerdo/entendimiento** (no solo precio):

- `turn_index`,
- `agreement_closeness_score_0_100`,
- `delta_vs_previous`,
- `direction` (`up|flat|down`).

Panel hover/lateral:

- extracto usuario,
- extracto contraparte,
- razón de impacto,
- efecto mental en contraparte,
- reformulación sugerida.

## D. Momentos clave

- mejor momento,
- momento más delicado,
- punto de giro.

Cada uno referencia turnos concretos + justificación.

## E. Recomendaciones

Dos niveles:

1. generales (principios transversales),
2. casos concretos con evidencia de turnos y reformulación mejorada.

## F/G/H

- fortalezas a repetir,
- próximo foco único para siguiente sesión,
- frase recomendada de cierre.

---

## Influencia de la demo actual

Existe una demo visual de feedback en `backend/avatar_app/demo_feedback_mode.js` con:

- overlay final,
- score/estrellas,
- cards,
- gráfico de turnos,
- momentos y recomendaciones.

Decisión v1: reutilizar su filosofía visual como referencia de composición, pero **no** su modelo de datos hardcodeado. El frontend productivo consumirá `ui_feedback_report_v1`.

## Requisitos de copy/tono

- lenguaje concreto y accionable,
- feedback firme pero no punitivo,
- foco en conducta observable por turno,
- evitar explicaciones “místicas” no trazables.
