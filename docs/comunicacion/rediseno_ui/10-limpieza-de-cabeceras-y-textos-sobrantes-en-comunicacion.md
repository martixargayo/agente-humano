# 10 · Limpieza de cabeceras y textos sobrantes en comunicación

## 1) Objetivo del doc
Inventariar pantalla por pantalla qué textos/cabeceras sobran en `comunicacion`, qué nodos exactos los generan y qué debe dejar de renderizarse en la siguiente fase.

## 2) Archivos inspeccionados
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/styles.css`

## 3) Evidencia exacta encontrada en el repo

## 3.1 Shell transversal que contamina todas las pantallas
El shell común inyecta copy global en todas las fases:
- `p.eyebrow`: `Comunicación · Captura`
- `h1#activityTitle`: default `Preparación de vídeo` y luego sobrescrito por `activity_brief.title` (ej. `Presentación breve grabada`).
- `p#activitySubtitle.communication-subtitle`: copy largo de configuración.

Además `renderApp()` actualiza siempre:
- `activityTitle`
- `setupContextSummary`
- `aidaContextSummary`

Por tanto el encabezado superior aparece en setup, AIDA, grabación, review, processing y report.

## 3.2 Inventario por pantalla

### Pantalla 1 · Setup/Permisos (`data-screen="setup"`)
Textos sobrantes detectados:
- Shell superior: `Comunicación · Captura`, título actividad, subtítulo de configuración.
- En panel: `Configura cámara y micrófono`.
- `#setupContextSummary`: texto explicativo largo.
- `#setupStatusText` estados narrativos largos.

Nodos exactos:
- `header.communication-header > .eyebrow`
- `#activityTitle`
- `#activitySubtitle`
- `#screenSetup .panel-copy h2`
- `#setupContextSummary`
- `#setupStatusText`

### Pantalla 2 · AIDA prep (`data-screen="aida_prep"`)
Textos sobrantes detectados:
- Sigue apareciendo cabecera shell (`Comunicación · Captura` y actividad).
- `h2` de panel + `#aidaContextSummary` pueden resultar redundantes frente al contenido editable.

Nodos exactos:
- Mismos 3 nodos de shell.
- `#screenAidaPrep .panel-copy h2`
- `#aidaContextSummary`

### Pantalla 3 · Grabación (`data-screen="recording"`)
Textos sobrantes detectados:
- Cabecera shell transversal completa.
- `Grabación guiada` + párrafo de apoyo.
- `Self-view` y `Guía AIDA` pueden recargarse según el nuevo layout deseado.

Nodos exactos:
- Shell (`.eyebrow`, `#activityTitle`, `#activitySubtitle`).
- `#screenRecording .panel-copy h2`
- `#screenRecording .panel-copy p`
- `.recording-section-title` (aparece varias veces)

### Pantalla 4 · Review/Enviar y evaluar (`data-screen="review"`)
Textos sobrantes detectados:
- Cabecera shell transversal.
- `Review` + párrafo explicativo.

Nodos exactos:
- Shell (`.eyebrow`, `#activityTitle`, `#activitySubtitle`).
- `#screenReview .panel-copy h2`
- `#screenReview .panel-copy p`

### Pantalla 5 · Uploading + Processing
`screenUploading` (intermedia):
- `Registrando metadata` + `#uploadStatusText` provoca la “pantallita intermedia” textual antes del loading final.

`screenProcessing`:
- No arrastra shell textual porque sigue dentro de shell mayor, pero visualmente hereda el contenedor principal (card general).

Nodos exactos:
- `#screenUploading .panel-copy h2`
- `#uploadStatusText`
- Estructura contenedora global `.communication-card.communication-card--shell`

### Pantalla 6 · Report/Feedback final (`data-screen="report"`)
Textos/acciones sobrantes detectados:
- Cabecera shell transversal.
- Botones manuales no deseados:
  - `#exportReportJsonBtn`
  - `#exportReportHtmlBtn`
  - `#exportReportPngBtn`
  - `#emitFinalResultBtn`
- Texto de estado no deseado:
  - `El resultado final se habilitará cuando el informe esté disponible.`

Nodos exactos:
- `#screenReport .panel-actions` (acciones manuales)
- `#finalResultStatusPanel` (mensajes de entrega)

## 4) Diagnóstico del estado actual
- El principal problema no está solo en una pantalla: es **arquitectural** por shell compartido.
- Mientras exista `header.communication-header` global dentro de `.communication-card--shell`, reaparece el ruido arriba en casi todo el flujo.
- El render central (`renderApp`) fuerza actualización de textos globales en cada rerender.

## 5) Extracción exacta de referencia de negociación (aplica como criterio)
- Negociación separa vistas full-screen (`app`, `loading`, `report`, `error`) mediante `showFeedbackView(mode)` y `classList.toggle('hidden', ...)`.
- No mantiene un header persistente equivalente durante loading/report.

## 6) Tabla de reutilización

| Pieza | Archivo origen | Reutilizar tal cual / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `show/hide` por vista completa | `interfaz_usuario_app/app.js` | Reutilizar patrón | Evita shell textual persistente | `comunicacion_app/app.js` transición entre screens |
| Header global comunicación | `comunicacion_app/index.html` | Descartar o condicionar por pantalla | Es fuente principal de ruido | Setup minimal + vistas limpias |
| `screenUploading` textual | `comunicacion_app/index.html` | Adaptar fuerte o descartar visual | Causa transición fea intermedia | Integrar directamente en loading real |

## 7) Tabla de intervención futura por archivo

| Archivo | Qué tocar | Qué eliminar | Qué conservar | Riesgo |
|---|---|---|---|---|
| `backend/comunicacion_app/index.html` | Reestructurar shell por pantalla | `header.communication-header` persistente, textos redundantes por panel | IDs funcionales de flujos y botones necesarios | Medio |
| `backend/comunicacion_app/app.js` | Condicionar render de títulos/subtítulos por pantalla o retirarlo | Escrituras forzadas a `activityTitle`/subresúmenes en todas las fases | Gestión de estado de capture/evaluation | Bajo-medio |
| `backend/comunicacion_app/styles.css` | Remover dependencias visuales de `.communication-card--shell` en loading/report | Estilos de `eyebrow`, `communication-subtitle` en flujos finales | Variables de color base | Bajo |

## 8) Criterio claro de cómo debe quedar después
- No deben verse arriba, en ninguna pantalla objetivo, textos tipo `Comunicación · Captura` ni derivados.
- Cada pantalla debe mostrar solo contenido estrictamente funcional al paso actual.
- Setup y feedback final deben quedar visualmente secos y directos, sin cabeceras heredadas.
