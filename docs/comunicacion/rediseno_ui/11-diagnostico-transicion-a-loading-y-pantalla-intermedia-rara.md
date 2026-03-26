# 11 · Diagnóstico transición a loading y pantalla intermedia rara

## 1) Objetivo del doc
Diagnosticar exactamente qué transición/vista intermedia aparece al pulsar `Enviar y evaluar`, por qué ocurre, y por qué la loading de `comunicacion` queda encapsulada en card/recuadro en vez de fondo blanco limpio como negociación.

## 2) Archivos inspeccionados
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/styles.css`
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`

## 3) Evidencia exacta encontrada en el repo

### 3.1 Secuencia real actual en comunicación
Al pulsar `#sendAndEvaluateBtn`:
1. `sendAndEvaluate()`
2. si falta `recording_id`, ejecuta `registerRecordingMetadata()`
3. `registerRecordingMetadata()` hace `transitionTo(SCREEN_UPLOADING)`
4. después `submitCommunicationAttempt()` hace `transitionTo(SCREEN_PROCESSING)`

Resultado: se ve `screenUploading` durante un instante antes de `screenProcessing`.

### 3.2 Markup exacto de vista intermedia “rara”
```html
<section id="screenUploading" class="communication-panel hidden" data-screen="uploading">
  <div class="panel-copy">
    <h2>Registrando metadata</h2>
    <p id="uploadStatusText">Estamos creando el attempt...</p>
  </div>
</section>
```

### 3.3 Handler/transición que la provoca
- `sendAndEvaluateBtn` → `sendAndEvaluate()`.
- `registerRecordingMetadata()` contiene `transitionTo(SCREEN_UPLOADING)`.
- `submitCommunicationAttempt()` contiene `transitionTo(SCREEN_PROCESSING)`.

El par de transiciones consecutivas, más el polling posterior, produce la transición visual “flash”.

### 3.4 Por qué loading queda “dentro de recuadro blanco”
`screenProcessing` está dentro de esta jerarquía:
- `<main class="communication-shell">`
  - `<section class="communication-card communication-card--shell">`
    - `<section id="screenProcessing" ...>`

`.communication-card` define borde, radio y sombra (`border`, `border-radius`, `box-shadow`). Aunque el contenido loading tenga estética propia, sigue enmarcado por el card padre.

## 4) Diagnóstico del estado actual
- El “intermedio raro” no es bug aleatorio: está codificado explícitamente como pantalla `uploading`.
- La falta de parity con negociación no está en `feedback-loading-layout` aislado, sino en el **contenedor padre** de comunicación que mantiene framing tipo card.

## 5) Extracción exacta de referencia de negociación si aplica

### 5.1 Loading de negociación (estructura)
```html
<section id="feedbackLoadingScreen" class="feedback-screen hidden" aria-live="polite">
  <div class="feedback-loading-layout">
    <div id="feedbackFloatingLayer" class="feedback-floating-layer"></div>
    <div class="feedback-loading-content">
      <div class="feedback-card">...</div>
    </div>
  </div>
</section>
```

### 5.2 Activación de vista en negociación
`showFeedbackView('loading')` oculta `#mainApp` y muestra solo `#feedbackLoadingScreen`.

Esto evita card-shell previo y evita transiciones textuales intermedias.

## 6) Tabla de reutilización

| Pieza | Archivo origen | Reutilizar tal cual / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `showFeedbackView(mode)` por secciones full-screen | `interfaz_usuario_app/app.js` | Reutilizar patrón | Elimina flashes intermedios | Control de vistas en `comunicacion` |
| `feedback-loading-layout` + floating layer | ambos apps | Reutilizar (ya casi igual) | Ya existe parity parcial | Mantener y sacar de card padre |
| `screenUploading` textual | `comunicacion_app/index.html` | Descartar visual intermedia | Genera “pantallita rara” | Integrar estado en loading principal |

## 7) Tabla de intervención futura por archivo

| Archivo | Qué tocar | Qué eliminar | Qué conservar | Qué riesgo hay |
|---|---|---|---|---|
| `backend/comunicacion_app/app.js` | Reencadenar transición directa a `processing` | `transitionTo(SCREEN_UPLOADING)` visible al usuario | Lógica de metadata/submit | Riesgo bajo (control de UX) |
| `backend/comunicacion_app/index.html` | Reubicar loading fuera de card shell o neutralizar shell en processing | Dependencia estructural de `communication-card` para loading | Estructura de `feedback-loading-layout` | Riesgo medio por layout global |
| `backend/comunicacion_app/styles.css` | Definir variante sin card/sombra para processing | Herencia de card en loading final | Animaciones loading actuales | Riesgo bajo-medio |

## 8) Criterio claro de cómo debe quedar después
- Al pulsar `Enviar y evaluar`, debe verse directamente loading principal sin pantalla textual intermedia.
- Loading final debe mostrarse en fondo blanco limpio, sin marco/card/sombra externa de shell.
- Debe existir paridad visual real con negociación (misma sensación de escena abierta, no tarjeta encapsulada).
