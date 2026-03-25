# Fix: separación de referencia interna de vídeo vs URL reproducible HTTP

## 1. Problema detectado
En el flujo `comunicacion`, el sistema estaba reutilizando `media.video_ref` para dos usos distintos:

- **Procesamiento backend** (STT, audio, visual), donde `file://...` es válido.
- **Reproducción en UI** (`<video>`), donde `file://...` falla en navegador embebido (Moodle).

Consecuencia observada: el player del informe final intentaba cargar `file:///tmp/...`, quedando en `00s` y con error de recurso local no permitido.

## 2. Causa raíz
La subida multiparte persistía el vídeo en `/tmp/comunicacion_uploads/...` y devolvía `video_ref=file://...`.
Ese `video_ref` se propagaba sin separación hasta `report.media.video_ref`, y el renderer final lo usaba directamente en `<source src="...">`.

## 3. Decisión técnica
Aplicar una separación mínima y compatible hacia atrás:

- Mantener `video_ref` como **referencia interna** para procesamiento backend.
- Introducir `playback_url` como **URL reproducible HTTP** para UI.
- Añadir endpoint de reproducción:
  - `GET /api/comunicacion/recordings/{recording_id}/video`

## 4. Cómo se separa referencia interna vs playback
- `video_ref` se mantiene intacto en storage/modelos para el pipeline multimodal.
- `playback_url` se deriva por `recording_id`:
  - Si `video_ref` ya es `http/https`, `playback_url` reutiliza ese valor.
  - En otros casos, `playback_url=/api/comunicacion/recordings/{recording_id}/video`.

## 5. Ruta HTTP creada
- **Nueva ruta:** `GET /api/comunicacion/recordings/{recording_id}/video`
- Comportamiento:
  - Busca el `RecordingRecord`.
  - Resuelve el archivo local cuando el `video_ref` es `file://` o ruta local.
  - Devuelve `FileResponse` con `media_type` del recording.

## 6. Archivos tocados
- `backend/comunicacion/api/router.py`
- `backend/comunicacion/services/recording_service.py`
- `backend/comunicacion/models.py`
- `backend/evaluacion/contracts/communication_models.py`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/engine/communication_report_assembler.py`
- `backend/comunicacion_app/report_view.js`
- `backend/tests/test_communication_public_upload_real_video.py`
- `backend/tests/test_communication_report_api.py`
- `backend/tests/test_communication_report_contract.py`
- `backend/tests/test_communication_report_renderer.py`

## 7. Tests ejecutados
- `pytest -q backend/tests/test_communication_public_upload_real_video.py`
- `pytest -q backend/tests/test_communication_report_api.py`
- `pytest -q backend/tests/test_communication_report_contract.py`
- `pytest -q backend/tests/test_communication_report_renderer.py`
- `pytest -q backend/tests/test_communication_report_exports_integrity.py`
- `pytest -q backend/tests/test_communication_final_result_contract.py`

## 8. Compatibilidad con pipeline/report/final_result
- El pipeline multimodal sigue usando `video_ref` interno (sin cambios de contrato de procesamiento).
- El report final ahora dispone de `media.playback_url` para reproducir vídeo por HTTP.
- `final_result` no se ha modificado funcionalmente; sigue serializando `video_ref` y `media.video_ref`.

## 9. Qué NO se ha tocado
- No se tocó bridge/embed/Moodle.
- No se cambió el protocolo de mensajería `final_result` / `final_result_saved`.
- No se rediseñó el report ni el frontend más allá de la selección segura de `src` del player.
