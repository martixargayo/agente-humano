# 05 · Pantalla de carga/evaluación idéntica a negociación (port literal)

## 1) Objetivo del doc
Documentar cómo portar literalmente la loading screen de negociación a comunicación: misma composición, mismos textos, mismas animaciones y misma lógica de activación visual.

## 2) Archivos/pantallas inspeccionados
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`

## 3) Evidencia exacta encontrada en repo

### 3.1 Markup exacto en negociación
- `#feedbackLoadingScreen`
- `.feedback-loading-layout`
- `#feedbackFloatingLayer`
- `.feedback-loading-content`
- `.feedback-card`
- `.feedback-title.feedback-title-shimmer`
- `.feedback-loading-stage` con `#feedbackLoadingText`

### 3.2 CSS/animaciones exactas
- `feedback-loading-layout::before` y `::after`
- `feedback-floating-line`
- `@keyframes feedbackTitleShimmer`
- `@keyframes feedbackLineOrbit`
- `@keyframes feedbackDotPulse`
- bloques `@media` y `prefers-reduced-motion`

### 3.3 JS de activación exacto
- `showFeedbackView('loading')`
- `startFeedbackFloatingPhrases()` / `stopFeedbackFloatingPhrases()`
- `setFeedbackStageText(status)` alimentado por `JobStageLabel`

### 3.4 Estado actual en comunicación
- `screenProcessing` actual es textual y técnica (`evaluation_id=...status=...stage=...`).

## 4) Diagnóstico del estado actual
- La pantalla de procesamiento de comunicación no está a nivel visual de negociación.
- Expone información interna no deseada para UX final.

## 5) Referencia visual/técnica exacta
La referencia es **1:1** la sección `feedbackLoadingScreen` de `interfaz_usuario`, incluyendo:
- estructura HTML,
- clase/animaciones CSS,
- texto principal y subtítulo,
- dinámica de frases flotantes y etapa.

## 6) Propuesta detallada de cómo debería quedar
- Reemplazar `screenProcessing` por un clon funcional de `feedbackLoadingScreen`.
- Mantener exactamente:
  - texto título: “Estamos evaluando tu desempeño...”,
  - subtítulo,
  - stage pill con punto,
  - motion design.
- No insertar bloques adicionales de información técnica.

## 7) Layout detallado
- Fondo blanco total.
- Capa de frases flotantes detrás.
- Card central con título shimmer y status line.
- Comportamiento responsive igual que negociación.

## 8) Tabla de reutilización

| Pieza actual | Archivo origen | Reutilizar / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `feedbackLoadingScreen` markup | `backend/interfaz_usuario_app/index.html` | Reutilizar tal cual (port literal) | requisito explícito de igualdad | pantalla loading comunicación |
| `feedback-loading-*` CSS | `backend/interfaz_usuario_app/index.html` | Reutilizar tal cual | misma sensación visual requerida | `comunicacion/styles.css` sección parity |
| `startFeedbackFloatingPhrases()` | `backend/interfaz_usuario_app/app.js` | Adaptar mínimo | depende de ids UI locales | `startCommunicationFloatingPhrases()` |
| `screenProcessing` texto técnico | `backend/comunicacion_app/index.html` | Descartar | no cumple criterio UX | reemplazado por loading parity |
| `pollEvaluationUntilReportReady()` | `backend/comunicacion_app/app.js` | Reutilizar | lógica backend ya válida | solo cambia presentación |

## 9) Tabla de implementación futura por archivo

| Archivo | Qué parte exacta tocar | Qué conservar | Qué eliminar | Qué añadir | Riesgo |
|---|---|---|---|---|---|
| `backend/comunicacion_app/index.html` | sección `screenProcessing` | contenedor general de pantallas | copy técnico actual | markup loading parity | Bajo |
| `backend/comunicacion_app/styles.css` | bloque de estilos loading | tokens de botón | estilos mínimos de processing | CSS idéntico negociación | Medio |
| `backend/comunicacion_app/app.js` | render/texto stage + timers visuales | polling evaluación actual | texto `evaluation_id=...` al usuario | funciones floating phrases | Bajo |

## 10) Riesgos o puntos delicados
- Port literal exige vigilar dependencias de ids para que no queden rotas.
- Asegurar que reduced-motion siga respetado.
- Evitar divergencias futuras: declarar esta sección como “parity contract”.

## 11) Criterio de aceptación visual/UX
- Captura comparativa lado a lado: comunicación loading = negociación loading.
- Misma narrativa visual, misma tipografía, mismas animaciones.
- Sin información técnica adicional para usuario final.
