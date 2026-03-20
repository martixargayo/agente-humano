# Ejecución fase 9: alineación contractual de `final_result` con Moodle

## Situación anterior

Antes de este ajuste, el simulador emitía hacia el padre un `final_result.payload` rico pero no compatible de forma exacta con lo que `mod/simulador` + `local_mynotebook` validan hoy.

El payload incluía, entre otros:

- `evaluation_id`
- `available_exports`
- `score_global_100`
- `stars_0_5`
- `activity_name`
- `interaction_outcome`
- `summary_2_3_lines`
- `report`
- `report_html`
- `summary_html`
- `report_json`
- `payloadjson`
- `reason`

Y el envelope transportaba fuera del payload:

- `session_id`
- `conversation_id`
- `context_id`
- `public_slug`

Además, el PNG final del informe solo existía como exportación manual descargable y no viajaba dentro de `final_result.payload`.

## Exigencia de Moodle

Moodle exige hoy en `final_result.payload`, con esos nombres exactos:

### Obligatorios

- `title`
- `activityid`
- `session_id`
- `summary_html`
- `snapshot_png_dataurl`
- `payloadjson`

### Opcionales relevantes

- `conversation_id`
- `trace_count`
- `context_id`
- `public_slug`
- `generated_at`

## Reparación aplicada

Se mantuvo el envelope embebido existente (`ns`, `v`, `type`, `event_id`, `correlation_id`, `session_id`, `conversation_id`, `context_id`, `public_slug`, `payload`) y se enriqueció `final_result.payload` para que también contenga los campos que Moodle valida dentro del propio payload.

### Campos añadidos al payload final

- `title`
- `activityid`
- `session_id`
- `conversation_id`
- `trace_count`
- `context_id`
- `public_slug`
- `generated_at`
- `snapshot_png_dataurl`

### Campos ricos preservados

- `evaluation_id`
- `available_exports`
- `score_global_100`
- `stars_0_5`
- `activity_name`
- `interaction_outcome`
- `summary_2_3_lines`
- `report`
- `report_html`
- `summary_html`
- `report_json`
- `payloadjson`
- `reason`

## Mapping final acordado

### `title`

Prioridad de resolución:

1. `report.header.report_title`
2. `report.header.activity_name`
3. fallback fijo: `Resultado final del simulador`

### `activityid`

Prioridad de resolución:

1. `public_slug`
2. `context_id`
3. `report.provenance.context_id`
4. `report.provenance.flow_id`
5. fallback fijo: `simulador`

Con este orden se privilegia un identificador funcional estable y público cuando existe (`public_slug`), sin perder fallback técnico en contextos internos.

### `session_id`

Se copia desde la metadata de sesión embebida al interior de `payload`, además de seguir existiendo en el envelope.

### `summary_html`

Se conserva el alias ya existente basado en la serialización HTML completa del informe.

### `payloadjson`

Se mantiene como **objeto JSON rico**, no como string serializada.

La razón es compatibilidad hacia atrás con el payload rico del simulador y consistencia con `report_json`, que ya apuntaba al objeto `report`. La serialización string sigue existiendo para descarga manual (`downloadReportJson`), pero no se usa en `final_result.payload`.

### `snapshot_png_dataurl`

Se añadió la generación de PNG embebido como Data URL reutilizando la ruta real de captura ya existente:

1. esperar estabilización de captura;
2. reutilizar `captureReportAsPng(report)`;
3. convertir el `Blob` PNG resultante a Data URL vía `FileReader`;
4. incrustar el resultado en `final_result.payload.snapshot_png_dataurl`.

Para robustez operativa, si la captura falla se usa un fallback PNG transparente 1x1 en Data URL. Eso evita volver a dejar al payload sin el campo obligatorio de Moodle.

## Cómo se estabiliza la captura PNG

Se añadió una espera explícita antes de la rasterización:

- `document.fonts.ready` cuando el navegador la soporta;
- dos `requestAnimationFrame` consecutivos.

Objetivo:

- capturar tras render completo;
- no depender de estados efímeros de hover;
- dejar que fuentes y layout se asienten antes del `foreignObject` + canvas;
- no romper la experiencia del usuario visible, ya que la captura ocurre en un root desacoplado y fuera de pantalla.

## Garantías demostradas con pruebas

Se añadieron validaciones automáticas para demostrar que:

- `buildFinalResultPayload(...)` genera `title`;
- `buildFinalResultPayload(...)` genera `activityid`;
- `buildFinalResultPayload(...)` genera `session_id` dentro de `payload`;
- `summary_html` sigue presente;
- `payloadjson` sigue presente;
- `snapshot_png_dataurl` queda presente con prefijo `data:image/png;base64,`;
- `generated_at` queda presente;
- `conversation_id`, `context_id`, `public_slug`, `trace_count` viajan también dentro de `payload` cuando existen;
- el envelope sigue conteniendo `ns`, `v`, `type`, `payload`;
- no se reintrodujo `postMessage('*')`;
- `final_result_available` sigue emitiéndose;
- las exportaciones manuales HTML/JSON/PNG siguen presentes en la superficie pública.

## Pruebas ejecutadas en esta fase

- test unitario/harness del contrato embebido con Node sobre funciones reales extraídas de `app.js`;
- test de serving público para verificar que `app.js` y `feedback_report_view.js` exponen el nuevo contrato y conservan las exportaciones manuales;
- suite de tests públicos de serving del frontend;
- búsqueda preventiva de `postMessage('*')`.

## Límites que siguen existiendo

- `payloadjson` se mantiene como objeto por compatibilidad funcional. Si Moodle decidiera exigir estrictamente string serializada, habría que adaptar ese punto contractual de forma explícita.
- La calidad visual exacta del PNG puede variar si una fuente remota no llega a cargarse en el momento de la captura; aun así, el contrato ya no falla porque el Data URL siempre se emite y existe un fallback seguro.
- `trace_count` depende de la metadata consolidada de sesión del runtime embebido. Si la sesión no se ha bootstrappeado correctamente, ese valor puede quedar `null`.

## Resultado final

Después de este ajuste, `final_result.payload` queda preparado para satisfacer los nombres obligatorios de Moodle sin perder la riqueza del payload original del simulador.
