# Fase 3 implementada — frames reales + evaluador visual real

## 1. Objetivo real de la fase
Activar evaluación visual basada en frames reales extraídos desde el video grabado, manteniendo compatibilidad con el contrato actual del report y del final_result.

## 2. Decisión técnica para extracción de frames
- Estrategia elegida: muestreo temporal uniforme con `ffmpeg` (`fps` derivado de `sample_every_ms`).
- Política por defecto aplicada:
  - `sample_every_ms = 1500`
  - `max_frames = 12`
  - `window_size = 4`
- Límite de coste: techo duro de frames por evaluación (`max_frames`) y ventanas acotadas.
- Trazabilidad: se genera `CommunicationFrameManifestV1` con `frame_id`, `timestamp_ms`, `frame_ref`, dimensiones y calidad básica.

## 3. Estrategia de batching
- Se agrupan frames consecutivos en ventanas (`CommunicationFrameWindow`) de tamaño fijo.
- Cada ventana conserva rango temporal (`start_ms` / `end_ms`) y referencias de evidencia (`frame_ids`).
- El evaluador visual consume estas ventanas para producir hallazgos temporales.

## 4. Cómo funciona el evaluador visual
- Se añadió un evaluador visual estructurado (`communication_visual_evaluator.py`) con salida `CommunicationVisualEvaluationV1`:
  - `score_0_100`
  - `subscores`
  - `temporal_findings`
  - `observations`
  - `recommendations`
  - `evidence_frames`
- Flujo real: usa `visual_features` con `frame_manifest` y `coverage_stats` para calcular subpuntuaciones trazables.
- Flujo degradado: si no hay extracción real de frames, devuelve evaluación estructurada degradada (sin romper contrato).

## 5. Archivos creados/modificados
### Creados
- `backend/evaluacion/engine/communication_frame_extractor.py`
- `backend/evaluacion/engine/communication_visual_evaluator.py`
- `backend/tests/test_communication_phase3_frames_and_visual.py`
- `docs/comunicacion/implementacion_multimodal/ejecucion/fase-3-implementada.md`

### Modificados
- `backend/evaluacion/contracts/communication_models.py`
- `backend/evaluacion/domains/communication/extractor.py`
- `backend/evaluacion/domains/communication/__init__.py`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/engine/communication_evaluators.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/comunicacion/storage/models.py`
- `backend/tests/test_communication_status_api.py`
- `backend/tests/test_communication_visual_placeholder.py`

## 6. Nuevos stages
Se añadieron stages de Fase 3:
- `frame_extraction_started`
- `frames_ready`
- `visual_analysis_started`
- `visual_analysis_ready`

## 7. Artefactos persistidos
Nuevos artefactos en repositorio:
- `frame_manifest` (manifest de frames extraídos)
- `visual_evaluation` (resultado visual estructurado)

Se mantienen artefactos previos (transcript/audio) y compatibilidad de report.

## 8. Tests ejecutados
- `python -m pytest backend/tests/test_communication_phase3_frames_and_visual.py -q`
- `python -m pytest backend/tests/test_communication_status_api.py -q`
- `python -m pytest backend/tests/test_communication_report_contract.py -q`
- `python -m pytest backend/tests/test_communication_final_result_contract.py -q`
- `python -m pytest backend/tests/test_communication_visual_placeholder.py -q`
- `python -m pytest backend/tests/test_communication_evaluation_job.py -q`

## 9. Qué NO se ha implementado todavía
- Fase 4 (síntesis global final de contenido + delivery + visual)
- Cambios en bridge/embed/final_result/Moodle
- Cambios de frontend en `backend/comunicacion_app/*`

## 10. Qué queda preparado para Fase 4
- `visual_features` real con frame manifest trazable y cobertura
- evaluación visual estructurada con evidencia temporal
- stages y artefactos de visual disponibles para futura síntesis global
