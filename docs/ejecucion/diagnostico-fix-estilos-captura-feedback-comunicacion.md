# Diagnóstico y fix de estilos en captura PNG del feedback de comunicación

## Síntoma observado
El `snapshot_png_dataurl` ya estaba capturando el contenido real del informe de comunicación, pero con presentación degradada: tipografía por defecto, layout apilado y pérdida de estilos de tarjetas/badges/grids.

## Evidencia literal de consola
- `[comm-report-capture] Sanitización aplicada antes de rasterizar. {removed_sections: 1, removed_nodes: 0}`
- Instrumentación de `Image.src` sobre el data URL SVG:
  - `isSvgDataUrl: true`
  - `hasStyleTag: true`
  - `hasFbCardClass: true`
  - `hasFeedbackDashboardClass: true`
  - `hasCommFeedbackRootClass: true`
  - `hasFontFamily: false`

## Qué ya estaba arreglado
La sanitización del subtree multimedia ya estaba activa en el happy path y removía el bloque que contiene `video`/metadatos antes de rasterizar, evitando la caída sistemática al fallback sintético.

## Causa raíz confirmada en código
En `backend/comunicacion_app/report_view.js`, la función `collectCaptureStyles()` filtraba reglas CSS por una lista muy restrictiva de selectores (`.comm-report`, `.comm-v3`, `.communication-report-placeholder`, `[data-report-root="true"]`).

Consecuencia directa:
- El SVG sí incluía un `<style>`, pero quedaban fuera reglas críticas reales del reporte (`.feedback-dashboard`, `.fb-card`, `.fb-grid-cards`, `.fb-badge`, etc.).
- También podía quedar fuera la tipografía global (`body`, `:root`).
- Resultado visual: HTML correcto con clases, pero sin tema/layout del simulador.

## Cómo se construía antes el SVG
El flujo `captureCommunicationReportPngDataUrlFromDom()` clonaba el root, lo saneaba, y luego llamaba a `buildCaptureSvgMarkup(clonedRoot, width, height)`; dentro de ese método se inyectaba `<style>${collectCaptureStyles()}</style>`.

El problema no era el `foreignObject` ni la serialización del DOM, sino la selección incompleta de reglas CSS embebidas.

## Ajuste aplicado
Se cambió la recolección de CSS para que sea contextual al `clonedRoot`:

1. `buildCaptureSvgMarkup(...)` ahora obtiene `const captureStyles = collectCaptureStyles(clonedRoot)`.
2. `collectCaptureStyles(captureRoot)` ahora:
   - incluye reglas globales necesarias (`html`, `body`, `:root`) para herencia tipográfica/base;
   - incluye reglas cuyo selector realmente aplica al subtree de captura (`captureRoot.matches(...)` o `captureRoot.querySelector(...)`);
   - procesa recursivamente reglas anidadas en `@media` y `@supports`;
   - preserva `@font-face`, `@keyframes`, `@page`, `@property` cuando están disponibles;
   - excluye selectores no relacionados con el informe.

Con esto, el SVG embebe los estilos reales del feedback que antes faltaban.

## Tests ejecutados
- `python -m unittest backend.tests.test_communication_snapshot_capture_path`

Además se amplió el harness en `test_communication_snapshot_capture_path.py` para verificar que:
- se embeben reglas de tipografía (`body { font-family: ... }`);
- se embeben reglas clave de layout/cards (`.feedback-dashboard`, `.fb-card`, `.fb-grid-cards`);
- no se cuelan selectores no relacionados.

## Veredicto final
Con el cambio aplicado, el happy path DOM→SVG→PNG mantiene la sanitización multimedia y además embebe el CSS necesario para preservar la estética real del feedback de comunicación. El fallback sintético sigue intacto y reservado para errores reales de rasterización/captura.
