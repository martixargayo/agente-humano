# Fase paralelización — implementada

## 1. Objetivo real del cambio

Reducir latencia de evaluación multimodal en `comunicacion` paralelizando:

- preparación de media (audio/frames) cuando es viable,
- evaluación de ramas `contenido`, `delivery` y `visual`,

manteniendo síntesis y ensamblado de report al final, sin cambios contractuales en `final_result` ni bridge/embed.

## 2. Decisión técnica aplicada

Se implementó una estrategia híbrida:

1. preflight media y resolución única de source,
2. extracción audio + extracción frames en paralelo en el builder,
3. STT sobre audio extraído,
4. cómputo de `audio_features` y `visual_features` con artefactos compartidos,
5. ejecución paralela de tres evaluadores en el service con `ThreadPoolExecutor`,
6. collector con timeout y degradación por rama,
7. síntesis global secuencial cuando las tres salidas ya están consolidadas.

## 3. Flujo antiguo vs flujo nuevo

### Antiguo

1. bundle secuencial (transcript → audio_features → visual_features),
2. evaluadores secuenciales (contenido → delivery → visual),
3. síntesis,
4. assembler report.

### Nuevo

1. preflight media,
2. media source único,
3. audio extraction + frame extraction en paralelo,
4. STT sobre audio,
5. audio_features + visual_features sobre artefactos pre-extraídos,
6. evaluadores en paralelo (contenido, delivery, visual),
7. síntesis global,
8. assembler report.

## 4. Cómo se lanzó la paralelización

- Builder:
  - `prepare_media_artifacts(...)` corre audio/frames en paralelo.
  - Si falla preflight paralelo, mantiene fallback existente.
- Service:
  - `_run_parallel_communication_analyses(...)` lanza futures explícitos para `evaluate_communication_content`, `evaluate_communication_delivery`, `evaluate_communication_visual`.
  - Se usa collector con timeout para consolidar resultados.

## 5. Gestión de errores parciales

Política implementada:

- excepción en una rama => fallback degradado de esa rama (`status_visual=placeholder`) + detalle en `details`,
- timeout de rama => cancelación + fallback degradado,
- si hay salidas mínimas de las tres ramas (reales o degradadas), el job continúa a síntesis y report,
- el job sólo falla completo en errores estructurales fuera de degradación controlada.

## 6. Stages finales

Se añadieron/ajustaron stages para observabilidad:

- `content_analysis_started`
- `content_analysis_ready`
- `delivery_analysis_started`
- `delivery_analysis_ready`
- `visual_analysis_started`
- `visual_analysis_ready`

Se mantienen `synthesis_started`, `synthesis_ready`, `assembling_report`, `completed`.

## 7. Archivos creados/modificados

Modificados:

- `backend/evaluacion/domains/communication/extractor.py`
- `backend/evaluacion/domains/communication/__init__.py`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/contracts/communication_models.py`
- `backend/tests/test_communication_status_api.py`

Creados:

- `backend/tests/test_communication_parallel_pipeline.py`
- `docs/comunicacion/implementacion_multimodal/ejecucion/fase-paralelizacion-implementada.md`

## 8. Tests ejecutados

- `python -m pytest backend/tests/test_communication_parallel_pipeline.py -q`
- `python -m pytest backend/tests/test_communication_evaluation_job.py -q`
- `python -m pytest backend/tests/test_communication_status_api.py -q`
- `python -m pytest backend/tests/test_communication_report_contract.py -q`
- `python -m pytest backend/tests/test_communication_report_exports_integrity.py -q`
- `python -m pytest backend/tests/test_communication_final_result_contract.py -q`

## 9. Compatibilidad con report/final_result

No se cambiaron contratos de:

- `UiCommunicationReportV1`,
- `exports.summary_html`,
- `exports.report_json`,
- `final_result` ni secuencia/ACK bridge.

Los cambios son internos de orquestación y resiliencia por rama.

## 10. Qué NO se tocó

- `backend/comunicacion_app/*`,
- bridge/embed/Moodle,
- contrato de `final_result`,
- estructura de report HTML/CSS del frontend público.
