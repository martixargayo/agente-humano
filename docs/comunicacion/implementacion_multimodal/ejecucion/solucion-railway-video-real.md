# Solución Railway directo: persistencia de vídeo real para pipeline multimodal

## 1. Problema real detectado

En el flujo público directo (`/comunicacion` y `/comunicacion/comunicacion`) la app registraba solo metadata y un `video_ref` temporal `client-temp://...`, sin subir el binario real al backend.

## 2. Causa raíz

`resolve_recording_media_source(...)` solo resuelve rutas locales existentes o `file://`. Al recibir `client-temp://...`, devolvía `recording_media_scheme_not_supported`, lo que activaba placeholders en transcript/audio/visual.

## 3. Decisión técnica tomada

- Mantener el endpoint existente `/api/comunicacion/attempts/{attempt_id}/upload`.
- Añadir soporte **multipart/form-data** para subir `video_file` real.
- Persistir archivo en disco temporal backend (`/tmp/comunicacion_uploads/...`).
- Guardar `video_ref` final como `file://...` absoluto.
- Mantener compatibilidad hacia atrás con JSON (flujo legado/degradado).

## 4. Cómo se persiste ahora el vídeo

- El frontend público envía `FormData` con `video_file` + metadata.
- El backend guarda bytes en `/tmp/comunicacion_uploads` con nombre único.
- El endpoint crea el recording con `video_ref=file://...`.

## 5. Cómo queda el `video_ref`

- **Nominal nuevo:** `file:///tmp/comunicacion_uploads/{attempt_id}_{id}.webm|mp4`
- **Fallback legado:** `client-temp://...` (si se usa payload JSON sin binario o falla subida binaria en cliente)

## 6. Cómo lo resuelve el backend

`resolve_recording_media_source(...)` ya soportaba `file://` y rutas locales. Con el nuevo `video_ref` persistido, la resolución entra por ruta nominal y deja de fallar por esquema.

## 7. Archivos tocados

- `backend/comunicacion_app/app.js`
- `backend/comunicacion/api/router.py`
- `backend/comunicacion/services/recording_service.py`
- `backend/tests/test_communication_public_upload_real_video.py`

Además se conservaron y ejecutaron los diagnósticos previos:
- `backend/tests/test_communication_railway_direct_placeholder_diagnosis.py`

## 8. Tests ejecutados

- `python -m pytest backend/tests/test_communication_railway_direct_placeholder_diagnosis.py -q`
- `python -m pytest backend/tests/test_communication_phase1_stt_and_content.py -q`
- `python -m pytest backend/tests/test_communication_phase2_audio_metrics_and_delivery.py -q`
- `python -m pytest backend/tests/test_communication_phase3_frames_and_visual.py -q`
- `python -m pytest backend/tests/test_communication_phase4_synthesis_and_report.py -q`
- `python -m pytest backend/tests/test_communication_report_contract.py -q`
- `python -m pytest backend/tests/test_communication_report_exports_integrity.py -q`
- `python -m pytest backend/tests/test_communication_final_result_contract.py -q`
- `python -m pytest backend/tests/test_communication_report_api.py -q`
- `python -m pytest backend/tests/test_public_comunicacion_serving.py -q`
- `python -m pytest backend/tests/test_communication_public_upload_real_video.py -q`

## 9. Compatibilidad con pipeline/report/final_result

- No se cambian contratos de `UiCommunicationReportV1`, `report_json`, `summary_html`, ni `final_result`.
- Se añadió únicamente una ruta nominal de ingestión real de media para que el pipeline pueda consumir `video_ref` resoluble.
- El modo degradado sigue disponible y controlado para entradas no resolubles.

## 10. Qué no se ha tocado

- Bridge/embed/Moodle.
- Contrato `final_result`.
- Diseño del report.
- Arquitectura general de Fase 1/2/3/4.

## 11. Veredicto final

Sí: el flujo público directo ya puede persistir vídeo real en backend y entregar un `video_ref` resoluble por el pipeline multimodal.

Esto elimina la degradación causada específicamente por `client-temp://...` cuando el upload binario multipart se completa correctamente.
