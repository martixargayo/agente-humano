# Comunicación — fase 5 implementada

## Objetivo real de la fase implementada

Esta fase transforma el report provisional de Fase 4 en un informe final de `comunicacion` usable por la persona usuaria y exportable sin entrar todavía en Fase 6.

El flujo que queda operativo es:

```text
submit -> processing -> report final con vídeo -> export JSON/HTML/PNG
```

## Archivos creados

- `backend/evaluacion/engine/communication_report_assembler.py`
- `backend/tests/test_communication_report_contract.py`
- `backend/tests/test_communication_report_renderer.py`
- `backend/tests/test_communication_report_export_contract.py`
- `backend/tests/test_communication_report_api.py`
- `docs/comunicacion/ejecucion/fase-5-implementada.md`

## Archivos modificados

- `backend/evaluacion/contracts/communication_models.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/report_view.js`
- `backend/comunicacion_app/styles.css`
- `backend/tests/test_communication_status_api.py`
- `backend/tests/test_public_comunicacion_app_assets.py`
- `backend/tests/test_public_comunicacion_serving.py`

## Contrato final de report implementado

`UiCommunicationReportV1` pasa a incluir:
- `header`
- `media`
- `video_panel`
- `block_cards`
- `timeline`
- `key_moments`
- `recommendations`
- `provenance`
- `exports`
- `placeholders`

## Assembler implementado

`backend/evaluacion/engine/communication_report_assembler.py`:
- convierte bundle + outputs de evaluadores en `UiCommunicationReportV1`
- construye el bloque `media` con `recording_id`, `video_ref`, `poster_frame_ref`, `duration_ms` y `player_hint`
- genera `timeline`, `key_moments` y `recommendations`
- serializa `summary_html`
- emite `report_json`
- adjunta `report_snapshot_png_data_url` como snapshot PNG básico/seguro compatible con la infraestructura actual

## Renderer final implementado

`backend/comunicacion_app/report_view.js` ahora expone:
- `renderCommunicationReport(root, report, options)`
- `renderCommunicationVideoPanel(media, panel, options)`
- `buildCommunicationReportSnapshotMarkup(report, options)`
- `serializeCommunicationReportToHtml(report)`
- `captureCommunicationReportPngDataUrl(report, options)`

## Integración explícita del vídeo dentro del informe

El informe final incluye un panel superior con reproductor pequeño:
- visible al comienzo de la lectura
- dentro del propio layout del informe
- acompañado de `recording_id` y `video_ref`
- pensado para que la persona contraste el vídeo con la evaluación mientras lee

## Exportables básicos implementados

### JSON
Se descarga desde frontend usando el propio payload del report final.

### HTML
Se genera con `serializeCommunicationReportToHtml(report)` a partir del markup del informe.

### PNG
Se genera con `captureCommunicationReportPngDataUrl(report, options)` usando un canvas resumen del informe.

## Qué queda explícitamente fuera de esta fase

No se implementa todavía:
- `final_result`
- embed final
- ACK final
- integración Moodle/cuaderno/LMS
- persistencia externa real del HTML o del PNG
- Fase 6

## Tests ejecutados

- `pytest -q backend/tests/test_communication_report_contract.py backend/tests/test_communication_report_renderer.py backend/tests/test_communication_report_export_contract.py backend/tests/test_communication_report_api.py`
- `pytest -q backend/tests/test_communication_bundle_builder.py backend/tests/test_communication_evaluation_job.py backend/tests/test_communication_status_api.py backend/tests/test_communication_visual_placeholder.py`
- `pytest -q backend/tests/test_comunicacion_attempt_repository.py backend/tests/test_comunicacion_recording_repository.py backend/tests/test_comunicacion_attempt_api.py backend/tests/test_comunicacion_session_refs.py backend/tests/test_comunicacion_bootstrap_api.py backend/tests/test_comunicacion_context_binding.py backend/tests/test_public_comunicacion_serving.py backend/tests/test_public_comunicacion_app_assets.py backend/tests/test_public_interfaz_usuario_serving.py backend/tests/test_phase8_second_official_context.py`

## Riesgos o decisiones pendientes

- el snapshot PNG sigue siendo una versión segura y simple, no una captura pixel-perfect del DOM
- `video_ref` continúa siendo una referencia opaca/provisional
- la persistencia y entrega a sistemas externos queda reservada para Fase 6
