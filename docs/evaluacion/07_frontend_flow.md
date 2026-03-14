# 07 — Frontend flow

## 0) Restricción de diseño

La integración en `interfaz_usuario` es **aditiva**:

- se reutiliza `finish_button_armed`,
- se añaden endpoints y estado UI para evaluación,
- no se altera lógica principal de turnos ni composición de mensajes.

## 1) Punto de partida real

`interfaz_usuario_app/app.js` ya gestiona:

- turnos por `/api/interfaz_usuario/negociacion/turn`,
- armado visual del botón finalizar,
- botón `finishNegotiationBtn` aún sin backend final.

## 2) Flujo UX productivo

1. Usuario pulsa `Finalizar conversación`.
2. Modal confirma acción irreversible de cierre + evaluación.
3. `POST /api/interfaz_usuario/feedback/evaluations`.
4. Navegar a `FeedbackLoadingScreen`.
5. Polling estado.
6. `completed` → cargar `GET .../report` y render.
7. `failed` → pantalla de error + retry.

## 3) Transición demo -> implementación real

## Se reutiliza de la demo (`demo_feedback_mode.js`)

- composición visual general:
  - header score/estrellas,
  - bloques,
  - gráfico trayectoria,
  - momentos y recomendaciones.

## NO se reutiliza

- datos hardcodeados (`TURN_SCORES`, cards estáticas, textos fijos),
- cálculo local ficticio del informe.

## Reemplazo

- fuente única de datos: `ui_feedback_report_v1` del backend.

## 4) Contrato consumido por UI

Siempre `ui_feedback_report_v1`.

La UI no debe:

- leer `feedback_report_core_v1` directo,
- leer `turn_trajectory_v1` directo,
- inferir reglas de negocio por su cuenta.

## 5) Hook recomendado

`useFeedbackEvaluation()`:

- `startEvaluation(sessionRef)`
- `pollStatus(evaluationId)`
- `fetchReport(evaluationId)`
- estado `{status, progressStage, error, report}`

## 6) Cambios mínimos en `interfaz_usuario_app/app.js`

- añadir modal confirmación,
- añadir handler real en `finishNegotiationBtn.onclick`,
- añadir polling y render de nuevo contenedor de reporte,
- mantener intacto handler de envío de turnos (`send.onclick`).

## 7) Criterios de no-regresión UI

- enviar turno sigue funcionando igual en todas las fases previas a cierre,
- `finish_button_armed` se respeta,
- si evaluación falla, conversación histórica no se pierde,
- no se bloquea interacción del chat por lógica de evaluación.
