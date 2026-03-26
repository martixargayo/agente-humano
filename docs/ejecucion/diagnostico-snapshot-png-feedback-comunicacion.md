# Diagnóstico técnico: PNG/snapshot de feedback de comunicación (simulador → Moodle/Mi cuaderno)

## 1) Síntoma observado (reconfirmado)

En **Mi cuaderno** se carga un PNG persistido real (`pluginfile.php/.../snapshot_*.png`) con dimensiones típicas de miniatura final (p.ej. ~1200x720), pero la imagen:

- no coincide con la plantilla completa del feedback visible en `simulador.gestionce.com`,
- muestra una versión resumida (título + score + recomendaciones),
- omite estructura/secciones/estilo del reporte renderizado.

Esto coincide con la evidencia que ya traías de navegador:

- `report_payload.placeholders.snapshot_png = "PNG placeholder estático hasta disponer de captura real del DOM en cliente."`
- y una imagen visualmente “sintetizada”.

## 2) Veredicto corto (causa raíz)

**El PNG que se envía a Moodle desde el simulador de comunicación NO es una captura real del DOM del feedback.**

En el flujo actual, el simulador construye el PNG con **Canvas 2D manual** (dibujando texto y bullets a mano), no con screenshot del reporte renderizado. Por eso se ve “genérico/simplificado” y no fiel al template real.

Además, en backend existe otro placeholder explícito (`1x1 PNG`) en `report.exports.report_snapshot_png_data_url`, reforzando que la captura fiel aún no estaba cerrada en servidor.

## 3) Flujo exacto actual de persistencia del snapshot

### 3.1 Punto de emisión de `final_result` en simulador (frontend comunicación)

Archivo: `backend/comunicacion_app/app.js`

- `buildCommunicationFinalResultPayload(...)` serializa:
  - `summary_html` usando `serializeCommunicationReportToHtml(report)`
  - `snapshot_png_dataurl` usando `captureCommunicationReportPngDataUrl(report, options)`
- luego ese payload se emite por bridge como `final_result`.

Referencia clave:

```js
const summaryHtml = global.CommunicationReportView.serializeCommunicationReportToHtml(report);
const snapshot = await global.CommunicationReportView.captureCommunicationReportPngDataUrl(report, options);
...
snapshot_png_dataurl: snapshot,
```

Conclusión: **el PNG persistido en Moodle depende directamente de `captureCommunicationReportPngDataUrl` de `comunicacion_app/report_view.js`.**

### 3.2 Cómo se genera hoy ese PNG en comunicación

Archivo: `backend/comunicacion_app/report_view.js`

Función: `captureCommunicationReportPngDataUrl(report, options = {})`

Implementación actual:

- crea canvas fijo (`width=1200`, `height=720` por defecto),
- pinta fondo blanco,
- dibuja manualmente:
  - título,
  - `summary_2_3_lines`,
  - `Score global`,
  - encabezado “Recomendaciones principales”,
  - hasta 3 recomendaciones,
- devuelve `canvas.toDataURL('image/png')`.

Esto **no inspecciona ni rasteriza** el DOM real del reporte (`.comm-report-v3`).

### 3.3 Estado backend (export placeholder)

Archivo: `backend/evaluacion/engine/communication_report_assembler.py`

- `_build_snapshot_png_data_url(...)` devuelve PNG base64 1x1 fijo.
- en `placeholders` se marca explícitamente:
  - `snapshot_png: 'PNG placeholder estático hasta disponer de captura real del DOM en cliente.'`

Esto demuestra que el contrato backend ya declara snapshot placeholder (servidor), y que la rasterización útil estaba prevista en cliente.

## 4) ¿Es captura real del DOM o placeholder artificial?

**No es captura real del DOM.**

Es una composición artificial programática basada en datos parciales del report.

Evidencia de código:

- La función de captura de comunicación no usa `html2canvas`, ni `foreignObject` con `clonedRoot`, ni serializa el nodo `.comm-report-v3` a imagen.
- Solo usa `CanvasRenderingContext2D.fillText(...)` con campos sueltos.

## 5) Qué partes del report usa hoy y qué ignora

### Usa hoy (sí aparece en PNG):

- `header.report_title`
- `header.summary_2_3_lines`
- `header.score_global_100`
- `recommendations.items` (máximo 3)

### Ignora o reduce fuertemente:

- layout real `.comm-report-v3`
- bloques AIDA completos
- visual de tarjetas/estados tal como renderiza el simulador
- panel de vídeo tal como se presenta en UI
- estilo real completo (`styles.css`) y jerarquía visual del reporte
- otras secciones que sí existen en markup serializado

## 6) Por qué el PNG final no coincide con la plantilla real

Porque se están mezclando dos representaciones distintas:

1. **Reporte visual real en UI**: generado por `buildCommunicationReportSnapshotMarkup(...)` (estructura HTML rica).
2. **PNG enviado al bridge**: generado por `captureCommunicationReportPngDataUrl(...)` dibujando un “resumen gráfico” manual de 1200x720.

Por diseño actual, (2) nunca podrá ser fiel a (1), aunque el bridge y Moodle funcionen perfecto.

## 7) ¿Existe en repo una ruta más fiel ya implementada?

Sí, en otro módulo de UI (`backend/interfaz_usuario_app/feedback_report_view.js`) hay pipeline de captura más completo:

- `captureReportAsPngPrimary` (clona DOM y rasteriza vía SVG/foreignObject),
- `captureReportAsPngFallback` (renderer SVG data-driven),
- preflight de estabilidad (`waitForStableReportCapture`, fuentes, imágenes),
- fallback controlado si falla el motor primario.

Eso confirma que la plataforma ya tiene un enfoque técnico más sólido para “captura de informe”, pero **no es el que usa hoy `comunicacion_app/report_view.js`**.

## 8) Fix mínimo correcto en simulador (recomendado)

Sin rediseño total, el camino mínimo robusto es:

1. En `backend/comunicacion_app/report_view.js`, reemplazar `captureCommunicationReportPngDataUrl(...)` por captura real del DOM del reporte (`.comm-report-v3`) renderizado.
2. Reutilizar patrón del módulo maduro (`feedback_report_view.js`):
   - render detached root,
   - esperar estabilidad de layout/fuentes,
   - rasterizar `outerHTML` en SVG/foreignObject,
   - convertir a PNG,
   - fallback explícito solo si falla.
3. Mantener como fallback extremo la versión simplificada actual (para no romper entrega), pero no como ruta principal.

### Impacto esperado del fix mínimo

- El PNG persistido en Moodle pasará a parecerse visualmente al feedback real del simulador.
- Se eliminará el gap actual “reporte rico vs imagen simplificada”.
- El problema se corrige en origen (simulador), sin culpar a Moodle.

## 9) Confirmación de alcance de responsabilidad

Con la trazabilidad de código actual, el problema del PNG no fiel está **en el simulador** (generación del `snapshot_png_dataurl`), no en Moodle:

- Moodle muestra el PNG persistido que recibe.
- El simulador está generando una miniatura simplificada en lugar de captura real del DOM.

## 10) Pruebas/checks ejecutados en esta investigación

- `rg -n "snapshot|placeholder|captureCommunicationReportPngDataUrl|snapshot_png|comm-report"`
  - para trazar funciones y contratos de export/captura.
- `python -m pytest backend/tests/test_communication_report_contract.py -q` ✅
- `python -m pytest backend/tests/test_snapshot_pipeline_validation.py -q` ✅
- `python -m pytest backend/tests/test_communication_report_exports_integrity.py -q` ✅

## 11) Conclusión final

El snapshot PNG que termina en Mi cuaderno es técnicamente válido como archivo, pero **es un render sintético parcial** y no un screenshot del feedback real.

La causa raíz no es el bridge ni Moodle: está en la función de captura del simulador de comunicación, que hoy genera una imagen manual simplificada.
