# Comunicación — fase 4 implementada

## Objetivo real de la fase implementada

Esta fase cierra el circuito mínimo real:

```text
review -> submit -> processing -> report placeholder
```

La implementación introduce un backend de evaluación mínimo, `evaluation_id`, estados/stages trazables, bundle consolidado, evaluadores placeholder honestos y un report JSON estable. No implementa renderer final bonito, exportables, embed final ni integración Moodle.

## Archivos creados

- `backend/comunicacion/services/evaluation_service.py`
- `backend/evaluacion/contracts/communication_models.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/engine/communication_evaluators.py`
- `backend/evaluacion/domains/communication/__init__.py`
- `backend/evaluacion/domains/communication/extractor.py`
- `backend/evaluacion/domains/communication/context_resolver.py`
- `backend/tests/test_communication_bundle_builder.py`
- `backend/tests/test_communication_evaluation_job.py`
- `backend/tests/test_communication_status_api.py`
- `backend/tests/test_communication_visual_placeholder.py`
- `docs/comunicacion/ejecucion/fase-4-implementada.md`

## Archivos modificados

- `backend/comunicacion/api/router.py`
- `backend/comunicacion/models.py`
- `backend/comunicacion/services/__init__.py`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/report_view.js`

## Endpoints añadidos

### `POST /api/comunicacion/attempts/{attempt_id}/submit`
- valida `user_id` y `session_id`
- valida ownership y existencia del `attempt`
- exige `recording_id`
- crea `evaluation_id`
- registra estado inicial `queued`
- lanza el pipeline mínimo de evaluación

### `GET /api/comunicacion/evaluations/{evaluation_id}`
Devuelve el estado del job con shape estable:
- `evaluation_id`
- `attempt_id`
- `status`
- `stage`
- `report_available`
- `error`

### `GET /api/comunicacion/evaluations/{evaluation_id}/report`
Devuelve `UiCommunicationReportV1`, un report JSON mínimo y estable para el placeholder visual de Fase 4.

## Contratos nuevos introducidos

### `CommunicationFeedbackInputBundleV1`
Bundle consolidado con:
- `evaluation_id`
- `session_ref`
- `attempt_ref`
- `domain_context`
- `recording`
- `transcript`
- `audio_features`
- `visual_features`

### Contratos auxiliares
- `CommunicationCoreEvaluatorInput`
- `CommunicationDeliveryEvaluatorInput`
- `CommunicationVisualEvaluatorInput`
- `CommunicationEvaluationStatusResponse`
- `UiCommunicationReportV1`

## Estados del job implementados

Estados altos:
- `queued`
- `running`
- `completed`
- `failed`

Stages:
- `queued`
- `extracting`
- `transcript_ready`
- `audio_features_ready`
- `visual_placeholder_ready`
- `assembling_report`
- `completed`
- `failed`

## Cómo se construye el bundle

`communication_bundle_builder.py`:
1. carga `AttemptRecord`
2. valida `recording_id`
3. carga `RecordingRecord`
4. resuelve `domain_context` desde el contexto oficial de `comunicacion`
5. construye placeholders honestos para transcript/audio/visual
6. devuelve `CommunicationFeedbackInputBundleV1`

## Cómo se modelan transcript/audio/visual placeholder

### Transcript
- `status: "placeholder"`
- `full_text: ""`
- `segments` mínimos derivados del `recording_id`
- `explanation` explícita indicando que no existe transcripción real todavía

### Audio features
- `status: "placeholder"`
- `speech_rate_wpm` sintético derivado de `duration_ms`
- `pause_segments` sintéticos mínimos
- `explanation` indicando que no hay extracción acústica real

### Visual
- `status: "placeholder"`
- `score_visual_0_100: null`
- `summary` y `explanation` explícitas indicando que la analítica visual avanzada no forma parte del MVP

## Qué flujo real queda operativo en frontend

`backend/comunicacion_app/app.js` ya conecta:

1. review local del vídeo
2. registro metadata (`upload`)
3. submit real con `POST /attempts/{id}/submit`
4. transición a `processing`
5. polling a `GET /evaluations/{id}`
6. carga final con `GET /evaluations/{id}/report`
7. render placeholder funcional vía `renderCommunicationReportPlaceholder(root, report)`

## Qué queda preparado para Fase 5

- report estable con bloques `content`, `delivery`, `visual`
- `evaluation_id` persistido como ref ligera en sesión
- renderer placeholder ya desacoplado en `report_view.js`
- media block disponible (`recording_id`, `video_ref`, `duration_ms`)

## Qué NO se ha implementado aún

- renderer final bonito
- vídeo pequeño arriba del informe final definitivo
- export HTML/PNG final
- `final_result`
- embed final
- integración Moodle
- storage binario real
- analítica visual real
- pipeline de media real
- Fase 5
- Fase 6

## Tests ejecutados

- `pytest -q backend/tests/test_communication_bundle_builder.py`
- `pytest -q backend/tests/test_communication_evaluation_job.py`
- `pytest -q backend/tests/test_communication_status_api.py`
- `pytest -q backend/tests/test_communication_visual_placeholder.py`
- `pytest -q backend/tests/test_comunicacion_attempt_repository.py backend/tests/test_comunicacion_recording_repository.py backend/tests/test_comunicacion_attempt_api.py backend/tests/test_comunicacion_session_refs.py backend/tests/test_comunicacion_bootstrap_api.py backend/tests/test_comunicacion_context_binding.py backend/tests/test_public_comunicacion_serving.py backend/tests/test_public_comunicacion_app_assets.py`
- `pytest -q backend/tests/test_public_interfaz_usuario_serving.py backend/tests/test_phase8_second_official_context.py`

## Riesgos o decisiones pendientes

- los jobs se ejecutan en proceso mediante `ThreadPoolExecutor`; es suficiente para el MVP pero no para cargas pesadas
- el report sigue siendo deliberadamente provisional y no pretende parecer un informe final
- `video_ref` continúa siendo una referencia opaca/provisional mientras no exista storage binario real
