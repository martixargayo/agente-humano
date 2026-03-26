# 07 · Análisis técnico de parpadeos (preview/captura)

## 1) Objetivo del doc
Analizar por qué pueden ocurrir parpadeos gigantes durante preview/grabación en `comunicacion`, identificando funciones/timers/listeners implicados y dejando plan de corrección futura (sin implementar).

## 2) Archivos/pantallas inspeccionados
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/styles.css`
- `backend/comunicacion_app/report_view.js`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/engine/communication_frame_extractor.py`
- `backend/evaluacion/engine/communication_media_processing.py`

## 3) Evidencia exacta encontrada en repo

### 3.1 Render de UI muy frecuente
- `startRecordingTimer()` ejecuta `setInterval(..., 250)`.
- En cada tick llama `renderApp()`.
- `renderApp()` llama `syncVideoElements()` y `syncDeviceSelects()` en cada ciclo.

### 3.2 Reasignación continua de stream a nodos video
- `syncVideoElements()` reasigna `previewVideo.srcObject = media_stream` y `recordingVideo.srcObject = media_stream` en cada render.
- En algunos navegadores, reasignar `srcObject` repetidamente puede provocar micro-cortes visuales/parpadeo.

### 3.3 Rehidratación completa de selects en cada render
- `hydrateDeviceSelect()` hace `select.innerHTML = ...` cada vez.
- Si esto ocurre a 4Hz durante grabación, puede generar reflow/repaint innecesario y “saltos” visuales de toda la pantalla.

### 3.4 Cambios de dispositivo reabren stream
- Listeners `videoDeviceSelect.change` y `audioDeviceSelect.change` llaman `openPreviewStream()`.
- `openPreviewStream()` primero llama `stopPreviewStream()` (para tracks) y luego nuevo `getUserMedia`.
- Si se dispara accidentalmente/repetido, hay cortes de video notorios.

### 3.5 Qué NO parece causa primaria de flicker en vivo
- `captureCommunicationReportPngDataUrl()` usa canvas, pero se ejecuta en export/report final, no en loop de grabación.
- Extracción de frames backend (`ffmpeg`) ocurre en evaluación, no en preview runtime de frontend.

## 4) Diagnóstico del estado actual
Hipótesis principal: **el parpadeo viene de rerender agresivo durante recording (250ms), con reasignación reiterada de `srcObject` y reconstrucción de selects**, más posibles recreaciones de stream en cambios de dispositivo.

## 5) Referencia visual/técnica exacta
- En `interfaz_usuario`, la UI de conversación evita repintar por completo la capa de video en cada tick: prioriza updates puntuales de estado.
- En comunicación actual, `renderApp()` mezcla actualización de texto/estado con nodos multimedia críticos en cada ciclo.

## 6) Propuesta detallada de corrección futura (sin implementación)

### 6.1 Separar render estructural de render de tiempo
- Mantener timer para etiqueta de tiempo, pero evitar `renderApp()` completo cada 250ms.
- Actualizar sólo `#recordingIndicator` en loop rápido.

### 6.2 Evitar reasignar `srcObject` si no cambió referencia
- Introducir guard clauses (comparar stream previo/actual).
- Reasignar sólo en eventos de cambio reales (`openPreviewStream`, stop/reset).

### 6.3 Evitar repintar selects en cada render
- Actualizar listas de dispositivos sólo al:
  - conceder permisos,
  - abrir popover,
  - evento `devicechange` o refresh explícito.

### 6.4 Instrumentación recomendada
- Añadir marca de rendimiento (`performance.now`) para:
  - número de renders por segundo,
  - número de reasignaciones `srcObject` por minuto,
  - número de reconstrucciones de select por minuto.

## 7) Layout detallado (impacto UX esperado)
- Eliminar parpadeo permitirá:
  - mantener self-view estable,
  - preservar sensación de “monitorización viva” sin ruido visual,
  - evitar fatiga/ansiedad al usuario durante grabación.

## 8) Tabla de reutilización

| Pieza actual | Archivo origen | Reutilizar / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `startRecordingTimer` | `backend/comunicacion_app/app.js` | Adaptar | útil para elapsed time | loop ligero sin rerender total |
| `renderApp` global | `backend/comunicacion_app/app.js` | Adaptar | hoy mezcla todo | separar render granular |
| `syncVideoElements` | `backend/comunicacion_app/app.js` | Adaptar | reasignación excesiva actual | update sólo en cambios reales |
| `hydrateDeviceSelect` | `backend/comunicacion_app/app.js` | Adaptar/descartar para UI final | rehidrata todo continuamente | selector moderno + updates bajo demanda |
| canvas report snapshot | `backend/comunicacion_app/report_view.js` | Reutilizar | no causa flicker de recording | export/report |

## 9) Tabla de implementación futura por archivo

| Archivo | Qué parte exacta tocar | Qué conservar | Qué eliminar | Qué añadir | Riesgo |
|---|---|---|---|---|---|
| `backend/comunicacion_app/app.js` | timer/render/sync multimedia | lógica recorder | rerender completo cada 250ms | render incremental y guards de stream | Alto |
| `backend/comunicacion_app/index.html` | nodos video/indicadores | ids video existentes | dependencia de selects en recording final | estructura control bar más estable | Medio |
| `backend/comunicacion_app/styles.css` | transiciones de video/estado | base de botones | estilos que acentúen flicker (si hubiese) | feedback visual sutil no invasivo | Bajo |

## 10) Riesgos o puntos delicados
- Cambios de render pueden introducir desincronizaciones si no se separan bien responsabilidades.
- Guardas de `srcObject` deben contemplar stop/restart y cleanup de tracks.
- Hay que validar en distintos navegadores (Chrome/Edge/Safari) porque `srcObject` no se comporta idéntico.

## 11) Criterio de aceptación visual/UX
- Durante grabación no hay flashes/saltos notorios de video.
- Timer e indicadores siguen actualizando en tiempo real.
- Cambiar dispositivo produce transición controlada, no parpadeo continuo.
