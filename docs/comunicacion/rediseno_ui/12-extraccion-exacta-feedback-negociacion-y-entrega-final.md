# 12 · Extracción exacta feedback negociación y entrega final

## 1) Objetivo del doc
Realizar mega diagnóstico del feedback de negociación: estructura HTML/JS/CSS exacta, estilo visual real, pipeline de entrega final automática y notificaciones, para reutilizarlo con máxima fidelidad en `comunicacion`.

## 2) Archivos inspeccionados
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/feedback_report_view.js`
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/report_view.js`

## 3) Evidencia exacta encontrada en el repo

### 3.1 Arquitectura de pantallas feedback en negociación
Pantallas separadas:
- `#feedbackLoadingScreen`
- `#feedbackReportScreen`
- `#feedbackErrorScreen`
- Toast global `#finalSaveToast`

Cambio de vistas:
- `showFeedbackView(mode)` alterna `hidden` entre `app/loading/report/error`.
- `startFeedbackEvaluation()` muestra loading y arranca polling.
- `pollEvaluationStatus()` lleva a report/error.

### 3.2 Loading visual exacto (negociación)
HTML:
- `feedback-loading-layout`
- `feedback-floating-layer`
- `feedback-loading-content`
- `feedback-card`
- `feedback-title feedback-title-shimmer`
- `feedback-loading-stage` con `feedback-stage-dot`

CSS clave:
- `.feedback-screen { position: fixed; inset:0; background:#FFF; }`
- `.feedback-loading-layout` con pseudo capas `::before`/`::after`
- `.feedback-floating-line` monoespaciado con tokens coloreados
- Sin card shell exterior permanente.

### 3.3 Plantilla de reporte final exacta (negociación)
`feedback_report_view.js`:
- Inyecta estilos por `ensureStyles()` con `<style id="feedback-report-view-styles">`.
- `renderReport(container, report)` construye:
  - `.feedback-dashboard`
  - header `.fb-card.fb-header`
  - bloque resultado `.fb-card.fb-result`
  - tarjetas por dimensión `.fb-grid-cards` + `.fb-skill-card`
  - chart `.fb-chart-card` + tooltip `.fb-turn-tooltip`
  - recomendaciones `.fb-recommendations`

Sistema visual exacto extraído:
- Tipografía: Inter.
- Fondo general blanco.
- Tarjetas con borde `#E4E7EC`, radio 16px, sombra suave.
- Jerarquía títulos 30/23/18/15 px aprox.
- Colores semáforo:
  - OK: verde `#16A34A`
  - Warn: ámbar `#D97706`
  - Bad: rojo `#DC2626`
- Grid de tarjetas 2 columnas con fallback mobile.

### 3.4 Notificaciones/toasts (negociación)
`app.js`:
- `showFinalSaveToast(message='Resultados guardados', durationMs=4200)`
- `hideFinalSaveToast()`
- elemento DOM: `#finalSaveToast`
- CSS: `.final-save-toast` + `.final-save-toast.visible`
- Mensaje de éxito se dispara al confirmar guardado embebido (ACK).

### 3.5 Entrega final automática (negociación)
Pipeline real:
1. `fetchEvaluationReport(evaluationId)`
2. `renderFinalReport(out.report)`
3. `await emitFinalResultLifecycle(out.report, { reason: 'report-fetched' })`

Es automática al cargar report, sin botón manual del usuario.

`emitFinalResultLifecycle()`:
- construye payload final (`buildFinalResultPayload()`)
- emite `final_result_available`
- emite `final_result` con `correlationId`
- registra ACK pendiente con `registerPendingEmbeddedFinalResultAck()`.

Al recibir ACK `final_result_saved` correlacionado:
- confirma estado
- muestra `showFinalSaveToast('Resultados guardados')`.

## 4) Diagnóstico del estado actual en comunicación

Diferencias críticas frente a negociación:
- Comunicación mantiene acciones manuales (`Exportar JSON/HTML/PNG`, `Entregar resultado final`) en `screenReport`.
- No hay auto-emisión al cargar report; se requiere click en `#emitFinalResultBtn`.
- El estado de entrega se muestra en panel textual (`#finalResultStatusPanel`) en vez de toast de éxito equivalente.
- La plantilla de reporte de comunicación (`report_view.js`) usa sistema `.comm-v3-*`, no `.fb-*`; jerarquía, ritmos y tarjetas no son parity exacta.

## 5) Extracción exacta de referencia de negociación (aplica)

### 5.1 Funciones críticas a reciclar conceptualmente
- `showFeedbackView(mode)`
- `startFeedbackEvaluation()`
- `pollEvaluationStatus()`
- `fetchEvaluationReport()`
- `emitFinalResultLifecycle()`
- `showFinalSaveToast()` / `hideFinalSaveToast()`
- `FeedbackReportView.renderReport()` y set de estilos inyectados.

### 5.2 Piezas visuales exactas a portar
- Sistema `.fb-card` y su escala de radios/sombras.
- Composición de `feedback-dashboard`.
- Semáforos de estado + badges.
- Densidad tipográfica y espaciados del reporte negociación.

## 6) Tabla de reutilización

| Pieza | Archivo origen | Reutilizar tal cual / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `emitFinalResultLifecycle(report)` automático | `interfaz_usuario_app/app.js` | Adaptar | Es negociación, payload distinto | Autoentrega en `comunicacion_app/app.js` al cargar report |
| `showFinalSaveToast()` | `interfaz_usuario_app/app.js` + css in `index.html` | Reutilizar patrón | UX de confirmación clara y no intrusiva | Sustituir panel textual en comunicación |
| `feedback_report_view.js` estructura `.fb-*` | `interfaz_usuario_app/feedback_report_view.js` | Adaptar fuerte | Dominios distintos, estilo objetivo común | Nueva versión de `comunicacion/report_view.js` |
| Botones manuales export/entrega | `comunicacion_app/index.html` | Descartar | Requisito explícito de autoentrega | Eliminar de pantalla final |
| `#finalResultStatusPanel` mensajes persistentes | `comunicacion_app/index.html`+`app.js` | Adaptar o descartar | Negociación usa toast+ACK, no panel fijo | Reemplazar por toast |

## 7) Tabla de intervención futura por archivo

| Archivo | Qué tocar | Qué eliminar | Qué conservar | Qué riesgo hay |
|---|---|---|---|---|
| `backend/comunicacion_app/index.html` | Reemplazar acciones manuales por contenedor de feedback limpio + toast | `exportReport*Btn`, `emitFinalResultBtn`, copy de habilitación manual | `reportPlaceholderRoot` (o equivalente) | Medio |
| `backend/comunicacion_app/app.js` | Disparar autoentrega al finalizar `fetchEvaluationReport()` | Dependencia de click manual en `emitFinalResultBtn` | Lógica actual de payload/hash/ACK | Medio |
| `backend/comunicacion_app/report_view.js` | Migrar estilo a patrón `.fb-*` equivalente negociación | Sistema actual `.comm-v3-*` si se busca paridad total | Utilidades de export HTML/PNG si sirven | Medio-alto por volumen visual |
| `backend/comunicacion_app/styles.css` | Alinear escala visual a negociación | Estilos que separan de referencia | Variables globales reutilizables | Medio |

## 8) Criterio claro de cómo debe quedar después
- Feedback final de comunicación debe verse con parity visual fuerte con negociación (tarjetas, espaciado, jerarquía, colorimetría).
- La entrega final debe ejecutarse automáticamente al tener report listo.
- Debe aparecer notificación estilo toast de confirmación (equivalente a `Resultados guardados`).
- No debe existir paso manual de exportar/entregar para el usuario final.
