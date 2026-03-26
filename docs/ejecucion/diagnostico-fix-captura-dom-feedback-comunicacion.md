# Diagnóstico + fix de captura DOM→PNG en feedback de comunicación

## 1) Síntoma observado

En ejecución real de `simulador.gestionce.com`, el `snapshot_png_dataurl` que termina persistido y consumido por Moodle / Mi cuaderno se estaba generando desde el fallback sintético, no desde captura fiel del DOM real del reporte.

Consecuencia observable: el PNG persistido mostraba una composición simplificada (título/score/recomendaciones), sin el layout real completo del feedback final.

## 2) Evidencia literal de consola usada como prueba

### 2.1 El root visual correcto sí existe y contiene el reporte real

Se verificó un root visible real con dimensiones completas (ej. `SECTION.comm-feedback-root` con ancho/alto > 1300x1600) y con subtree no vacío.

### 2.2 El subtree incluye tarjetas reales + panel de vídeo

La inspección de nodos reportó presencia simultánea de:

- `DIV.feedback-dashboard`
- `HEADER.fb-card.fb-header`
- `SECTION.fb-card.fb-section`
- `ARTICLE.fb-card.fb-skill-card`
- `VIDEO.fb-video`
- `DL.comm-report__video-meta`

### 2.3 El fallo real ocurre en rasterización (`img.onerror`)

Log literal observado en runtime:

- `[comm-report-capture] Falló captura DOM real; se usará fallback sintético. Error: No se pudo rasterizar el DOM del informe a PNG. at img.onerror (report_view.js:345:34)`

Esto confirma que el flujo **sí intenta** DOM real y falla durante `DOM -> SVG/foreignObject -> Image`.

### 2.4 El flujo real recibe un wrapper de pantalla como root de entrada

Instrumentación runtime confirmó que se pasa `DIV.communication-report-screen-root` como `options.rootElement` y ese wrapper contiene vídeo.

### 2.5 Prueba manual sin vídeo sí rasteriza

Al clonar el root y eliminar `video`, `.fb-video`, `.comm-report__video-meta`, la llamada a `captureCommunicationReportPngDataUrl(...)` devolvió PNG válido.

## 3) Diagnóstico en código (repo)

### 3.1 Dónde se construye y usa el root real del flujo

- El contenedor de pantalla es `#reportPlaceholderRoot.communication-report-screen-root` en `backend/comunicacion_app/index.html`.
- El reporte se renderiza en ese root desde `renderApp()` vía `CommunicationReportView.renderCommunicationReport(...)` en `backend/comunicacion_app/app.js`.
- El envío de `final_result` invoca `emitCommunicationFinalResultLifecycle(..., { rootElement: $('reportPlaceholderRoot') })`.

### 3.2 Ruta de captura DOM real

En `backend/comunicacion_app/report_view.js`:

- `captureCommunicationReportPngDataUrl(...)` intenta `captureCommunicationReportPngDataUrlFromDom(...)` y solo cae a fallback en excepción.
- `captureCommunicationReportPngDataUrlFromDom(...)`:
  - resuelve root vivo (`options.rootElement.querySelector('[data-report-root="true"]') || options.rootElement`)
  - clona root
  - serializa a SVG con `<foreignObject>`
  - rasteriza vía `Image` (`img.onerror` lanza error)

### 3.3 Papel exacto del bloque de vídeo

`buildCommunicationReportSnapshotMarkup(...)` incluye explícitamente en el árbol de snapshot:

- `<video class="fb-video" ...>`
- `<dl class="comm-report__video-meta">...`

Ese subtree de media era parte del clone rasterizado y coincide con la evidencia de consola (falla al cargar imagen del SVG serializado).

## 4) Diferencia con el caso de negociación

Este caso no es “root vacío / caja blanca” como otros escenarios.
Aquí el root real sí está poblado y visible; el fallo aparece en rasterización por contenido problemático del subtree (media embebida), no por ausencia de render.

## 5) Ajuste aplicado

Se implementó sanitización **previa a rasterización** sobre el clone (no sobre DOM vivo):

- Nueva función: `sanitizeCaptureCloneForRasterization(clonedRoot)`.
- Elimina secciones `.fb-card.fb-section` que contengan media problemática:
  - `video`, `audio`, `iframe`, `object`, `embed`, `.comm-report__video-meta`.
- Elimina además nodos media residuales por selector directo.
- Se invoca en el happy path, antes de construir SVG.

Con esto:

- Se mantiene captura DOM real como ruta principal.
- Se evita que el bloque de vídeo rompa `img.onerror`.
- El fallback sintético sigue intacto como red de seguridad.
- No se toca el contrato de `final_result` ni bridge/persistencia.

## 6) Tests / validaciones ejecutadas

1. `backend/tests/test_communication_snapshot_capture_path.py`
   - Verifica happy path (DOM) y fallback en error.
   - Añade validación de que el flujo llama la sanitización antes de rasterizar.
   - Incluye harness Node para probar que la sanitización elimina sección media + nodos media.

2. `backend/tests/test_communication_final_result_contract.py`
   - Verifica que `snapshot_png_dataurl` sigue presente y contrato final no se rompe.

## 7) Veredicto final

- Causa raíz confirmada: rasterización fallida por subtree de media (panel de vídeo/metadata) dentro del root capturado en el happy path DOM.
- Fix aplicado: sanitización del clone para excluir bloque problemático antes de SVG/foreignObject.
- Resultado esperado: el PNG persistido vuelve a provenir del DOM real del feedback (sin caer sistemáticamente al fallback), preservando el flujo completo de `final_result`.
