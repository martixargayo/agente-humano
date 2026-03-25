# Cierre del bridge embed `comunicacion` para alineación Moodle

## 1) Decisión contractual tomada (fuente de verdad)

Se fija de forma operativa este contrato:

1. `final_result_available` se mantiene y se emite antes de `final_result`.
2. `final_result` mantiene obligatorios `summary_html`, `snapshot_png_dataurl` y `payloadjson`.
3. El ACK `final_result_saved` solo se acepta si:
   - `ns === "gestionce.simulator"`
   - `v === 1`
   - `type === "final_result_saved"`
   - `session_id` coincide
   - `activityid` coincide
   - `payload_hash` coincide **obligatoriamente**
4. `evaluation_id` y `correlation_id` se conservan como correladores complementarios (ya no sustituyen `payload_hash`).
5. En embed real (`embed=1` + runtime embebido) `parent_origin` debe estar explícitamente configurado; si falta, se considera error de configuración (`embed_parent_origin_missing`).

## 2) Cambios exactos de código aplicados

## `backend/comunicacion_app/app.js`

- Se endureció ACK en `handleCommunicationEmbeddedSaveAck(...)`:
  - continúa exigiendo `session_id` y `activityid`.
  - ahora exige también `payload_hash` presente y coincidente para aceptar.
  - `evaluation_id` y `correlation_id` quedan como señales complementarias de trazabilidad.
- Se endureció `parent_origin`:
  - `readEmbedOriginFromUrl()` ahora devuelve `null` cuando no se informa.
  - `isAllowedParentOrigin()` rechaza cuando no hay `parent_origin` configurado.
  - `emitCommunicationFinalResultLifecycle(...)` en embed válido corta con error `embed_parent_origin_missing` si falta `parent_origin`, y no emite mensajes al parent.

## `backend/tests/test_comunicacion_embed_final_result_contract.py`

- Nuevas aserciones:
  - ACK con `session_id + activityid + evaluation_id` sin `payload_hash` => rechazado.
  - ACK con `session_id + activityid + correlation_id` sin `payload_hash` => rechazado.
  - ACK con `session_id + activityid + payload_hash` correcto => aceptado.
  - embed con `parent_origin` ausente => error `embed_parent_origin_missing` y `sentCount=0`.
- Se mantiene validación de secuencia:
  - `final_result_available`
  - `final_result`

## 3) Nuevas reglas de ACK (resumen operativo)

- Validación mínima de aceptación:
  - cabecera (`ns`, `v`, `type`)
  - `pending_ack` activo
  - éxito (`status=ok` o `saved=true`)
  - `session_id` match
  - `activityid` match
  - `payload_hash` match obligatorio
- Si falta o no coincide `payload_hash`, el ACK se rechaza.

## 4) Nueva regla de `parent_origin` (resumen operativo)

- Standalone (no embed): se preserva comportamiento actual; no hay `postMessage` a parent.
- Embed real: `parent_origin` obligatorio.
- Embed real sin `parent_origin`: error `embed_parent_origin_missing`, sin emisiones al parent y sin aceptación útil de ACK.

## 5) Tests ejecutados

- `python -m pytest backend/tests/test_comunicacion_embed_final_result_contract.py -q`
- `python -m pytest backend/tests/test_communication_final_result_contract.py -q`
- `python -m pytest backend/tests/test_communication_report_exports_integrity.py -q`

## 6) Qué no se ha cambiado

- Namespace/version del envelope (`gestionce.simulator`, `v=1`).
- Emisión de `final_result_available` (se mantiene).
- Preservación obligatoria de `summary_html`, `snapshot_png_dataurl`, `payloadjson` en `final_result`.
- Alcance del repositorio: no se implementa persistencia Moodle real ni backend LMS.
