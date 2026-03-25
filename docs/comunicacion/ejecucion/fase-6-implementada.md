# Fase 6 implementada — cierre del bridge final de `comunicacion`

## 1. Objetivo real de la fase implementada

La Fase 6 quedó implementada como un **bridge final embebible** para el flujo `comunicacion`. Su objetivo real no fue integrar Moodle ni crear persistencia LMS real, sino dejar listo el último tramo contractual para que el contenedor padre pueda recibir un `final_result` autocontenido, reconocerlo por correlación contractual y responder con un ACK `final_result_saved` sin perder los artefactos clave del informe final.

En términos concretos, esta fase cerró tres responsabilidades:

1. **emitir un payload final estable y autocontenido** desde `backend/comunicacion_app/app.js`
2. **preservar los artefactos exportables del informe** dentro del propio `final_result`
3. **correlacionar un ACK de guardado** mediante `session_id`, `activityid` y match obligatorio de `payload_hash` (con `evaluation_id` y `correlation_id` como correladores complementarios)

## 2. Archivos creados

- `backend/comunicacion/final_result_models.py`
- `backend/tests/test_comunicacion_embed_final_result_contract.py`
- `backend/tests/test_communication_final_result_contract.py`
- `backend/tests/test_communication_report_exports_integrity.py`
- `docs/comunicacion/ejecucion/fase-6-implementada.md`

## 3. Archivos modificados

- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/styles.css`

## 4. Shape final exacto del payload emitido

El payload final emitido por `buildCommunicationFinalResultPayload(report, options)` es este shape efectivo:

```json
{
  "schema_version": "comunicacion_final_result.v1",
  "activity_type": "comunicacion",
  "title": "Evaluación de tu comunicación oral",
  "activityid": "comunicacion",
  "session_id": "<session_id>",
  "user_id": "<user_id>",
  "attempt_id": "<attempt_id>",
  "recording_id": "<recording_id>",
  "evaluation_id": "<evaluation_id>",
  "context_id": "<context_id>",
  "public_slug": "comunicacion",
  "summary_html": "<html serializado del report>",
  "snapshot_png_dataurl": "data:image/png;base64,...",
  "payloadjson": {"...": "report final exportado en JSON"},
  "video_ref": "<video_ref>",
  "poster_frame_ref": "<poster_frame_ref|null>",
  "duration_ms": 12345,
  "created_at": "<iso8601>",
  "payload_hash": "fnv1a:........",
  "media": {
    "video_ref": "<video_ref>",
    "poster_frame_ref": "<poster_frame_ref|null>",
    "duration_ms": 12345,
    "mime_type": "video/mp4"
  }
}
```

Ese payload viaja dentro de un envelope:

```json
{
  "ns": "gestionce.simulator",
  "v": 1,
  "type": "final_result",
  "correlation_id": "<session_id>:final:<evaluation_id>:<payload_hash>",
  "session_id": "<session_id>",
  "context_id": "<context_id>",
  "public_slug": "comunicacion",
  "payload": { "...payload anterior..." }
}
```

## 5. Cómo se preservan los artefactos obligatorios

### `summary_html`
Se serializa con `CommunicationReportView.serializeCommunicationReportToHtml(report)` y se guarda directamente en `summary_html`. No se referencia de forma indirecta: queda embebido en el propio payload final.

### `snapshot_png_dataurl`
Se genera con `CommunicationReportView.captureCommunicationReportPngDataUrl(report, options)` y se guarda como `snapshot_png_dataurl`, por lo que el `final_result` preserva una representación visual final autocontenida del informe.

### `payloadjson`
Se toma de `report.exports.report_json` cuando existe; si no, cae al objeto `report` completo. Eso deja el JSON final del informe preservado sin depender del contenedor padre.

### `video_ref`
Se copia en el nivel superior del payload y además se duplica dentro de `media.video_ref` para que el contrato sea claro tanto para consumo directo como para consumo agrupado por media.

### `poster_frame_ref`
Se preserva en el nivel superior y también en `media.poster_frame_ref`.

### `duration_ms`
Se preserva en el nivel superior y en `media.duration_ms`.

### `evaluation_id`
Se conserva como identificador principal del resultado evaluado y además se usa como uno de los ejes de correlación fuerte del ACK.

### `attempt_id`
Se propaga desde `state.attempt.attempt_id` o desde el `report` final si ya viene rehidratado.

### `recording_id`
Se propaga desde `report.recording_id` o desde `report.media.recording_id`.

### `payload_hash`
Se deriva de un subconjunto estable del payload final usando `stableStringifyForHash(...)` + `simpleHashString(...)`. En el remate final de Fase 6 se dejó explícitamente calculado sobre:

- `activity_type`
- `title`
- `activityid`
- `session_id`
- `attempt_id`
- `recording_id`
- `evaluation_id`
- `payloadjson`
- `summary_html`
- `snapshot_png_dataurl`
- `video_ref`
- `poster_frame_ref`
- `duration_ms`

Esto hace que el hash refleje de forma más directa los artefactos y referencias que realmente se quieren preservar.

## 6. Cómo funciona el bridge final

El bridge final funciona así:

1. el usuario llega a la pantalla de informe (`screenReport`)
2. el botón **“Entregar resultado final”** llama a `emitCommunicationFinalResultLifecycle(...)`
3. esa función construye el payload final con HTML, PNG, JSON y refs de media
4. si no hay runtime embebido, el estado queda en `ready` y no intenta integrarse con ningún LMS
5. si sí hay contenedor embebido, exige `parent_origin` explícito; si falta, falla con `embed_parent_origin_missing`
6. en embed válido, emite primero `final_result_available` como evento de disponibilidad
7. luego emite el envelope `final_result` con `window.parent.postMessage(...)`
8. el estado visual pasa a `sending` y se registra un ACK pendiente en `state.final_delivery.pending_ack`

No se hace ninguna persistencia externa real desde este repo; solo se emite el contrato final.

## 7. Cómo funciona el ACK correlacionado

El listener `installCommunicationEmbedMessageListener()` escucha mensajes `postMessage` del padre y delega en `handleCommunicationEmbeddedSaveAck(...)`.

Un ACK solo se acepta si cumple todas estas condiciones:

1. `ns === "gestionce.simulator"`
2. `v === 1`
3. `type === "final_result_saved"`
4. el `origin` coincide con `parent_origin` (en embed válido debe venir configurado)
5. existe un `pending_ack` activo
6. el payload indica éxito (`status === "ok"` o `saved === true`)
7. coinciden `session_id` y `activityid`
8. `payload_hash` está presente y coincide con el pending ACK
9. `evaluation_id` y `correlation_id` se consideran correladores complementarios útiles, pero no sustituyen `payload_hash`

Cuando eso ocurre:

- `pending_ack` pasa a `false`
- `ack_confirmed` pasa a `true`
- el estado visual pasa a `ack_received`
- se guarda metadata mínima en `ack_meta`

## 8. Qué queda conscientemente fuera por depender del repo Moodle

Se dejó explícitamente fuera de este repo:

- el guardado real en Moodle
- endpoints LMS reales
- mapping definitivo a tablas/columnas del plugin Moodle
- versionado o storage real del `entryid`
- autenticación/autoría LMS
- reintentos transaccionales contra Moodle
- persistencia externa del ACK

La Fase 6 implementada aquí deja preparado el contrato y la correlación, pero **no implementa el lado Moodle**.

## 9. Tests ejecutados

Se ejecutaron los tests de cierre y regresión más relevantes para esta fase:

- `backend/tests/test_comunicacion_embed_final_result_contract.py`
- `backend/tests/test_communication_final_result_contract.py`
- `backend/tests/test_communication_report_exports_integrity.py`
- `backend/tests/test_communication_report_export_contract.py`
- `backend/tests/test_communication_report_renderer.py`
- `backend/tests/test_public_comunicacion_serving.py`
- `backend/tests/test_embed_final_result_contract.py`

## 10. Riesgos o decisiones pendientes

1. **`payloadjson` depende del report ensamblado disponible**: si en el futuro cambia el export JSON canónico del informe, el `final_result` cambiará también, y con ello el `payload_hash`.
2. **El PNG es un snapshot data URL**: esto favorece autocontención, pero puede crecer de tamaño si el informe final se vuelve mucho más pesado.
3. **No hay persistencia de ACK en backend**: el ACK confirmado vive en el estado del frontend embebido, lo cual es suficiente para esta fase, pero no sustituye una auditoría persistida.
4. **`parent_origin` es obligatorio en embed real**: sin ese parámetro el bridge devuelve `embed_parent_origin_missing` y no emite mensajes al parent.
5. **La aceptación del ACK exige `payload_hash`**: `evaluation_id` y `correlation_id` quedan como metadatos complementarios para trazabilidad.
