# Auditoría técnica — paralelización y pipeline multimodal de `comunicacion`

## 1. Objetivo de la auditoría

Comprobar con evidencia ejecutable que el pipeline actual:

1. opera de punta a punta (video_ref → report),
2. ejecuta ramas `contenido` / `delivery` / `visual` en paralelo,
3. respeta orden `ramas -> síntesis -> assembler`,
4. degrada correctamente ante fallos parciales,
5. mantiene compatibilidad contractual (`UiCommunicationReportV1`, exports y `final_result`).

## 2. Archivos inspeccionados

- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/domains/communication/extractor.py`
- `backend/evaluacion/contracts/communication_models.py`
- `backend/evaluacion/engine/communication_synthesis.py`
- `backend/evaluacion/engine/communication_report_assembler.py`
- `backend/tests/test_communication_parallel_pipeline.py`
- `backend/tests/test_communication_evaluation_job.py`
- `backend/tests/test_communication_report_contract.py`
- `backend/tests/test_communication_report_exports_integrity.py`
- `backend/tests/test_communication_final_result_contract.py`
- `backend/tests/test_communication_status_api.py`

## 3. Qué se verificó en el código

- Orquestación paralela real en service con futures por rama (`contenido`, `delivery`, `visual`) y collector con timeout/fallback.
- Stages explícitos por inicio/fin de cada rama y secuencia posterior de síntesis y ensamblado.
- Builder con preflight de media y preparación en paralelo audio/frames para reducir reproceso.
- Contratos de report/export/final_result sin modificación de shape público.

## 4. Tests ejecutados

- `python -m pytest backend/tests/test_communication_parallel_pipeline.py -q`
- `python -m pytest backend/tests/test_communication_evaluation_job.py -q`
- `python -m pytest backend/tests/test_communication_status_api.py -q`
- `python -m pytest backend/tests/test_communication_report_contract.py -q`
- `python -m pytest backend/tests/test_communication_report_exports_integrity.py -q`
- `python -m pytest backend/tests/test_communication_final_result_contract.py -q`
- `python -m pytest backend/tests/test_communication_phase1_stt_and_content.py -q`
- `python -m pytest backend/tests/test_communication_phase2_audio_metrics_and_delivery.py -q`
- `python -m pytest backend/tests/test_communication_phase3_frames_and_visual.py -q`
- `python -m pytest backend/tests/test_communication_phase4_synthesis_and_report.py -q`

## 5. Evidencia de paralelización real

Se reforzó el harness de `test_communication_parallel_pipeline.py` para demostrar:

- solape temporal entre ramas (barrier + timestamps),
- síntesis arranca solo al finalizar las 3 ramas,
- assembler arranca después de síntesis.

Se observaron resultados en verde en los tests.

## 6. Evidencia de orden correcto del pipeline

Verificado por test y por implementación:

1. preflight/media prep en builder,
2. construcción de transcript/audio/visual features,
3. ramas paralelas,
4. síntesis global,
5. assembler report,
6. exports y report disponibles.

## 7. Evidencia de degradación parcial

Se verificó degradación controlada para:

- excepción en `contenido`,
- excepciones en `delivery` y `visual`,
- timeout en rama (fallback sin abortar todo el job).

En estos casos el job continúa, produce report válido y marca bloque(s) degradado(s).

## 8. Compatibilidad contractual (no rotura)

Los tests de contrato/compatibilidad ejecutados y en verde evidencian:

- `UiCommunicationReportV1` estable,
- `exports.summary_html` y `exports.report_json` estables,
- contrato `final_result` estable.

## 9. Riesgos detectados (concurrencia)

### No críticos

1. **Orden de stages intermedios dependiente de timing**: con ramas paralelas, el último stage visible de rama puede variar por carrera de finalización.
2. **Error parcial en estado final del job**: la información detallada de fallo parcial se usa durante ejecución, pero el estado final `completed` prioriza éxito global del job.

No se observaron fallos críticos de consistencia contractual ni de generación de report.

## 10. Veredicto final

- **Bien paralelizado**: sí, con evidencia temporal y collector de ramas.
- **Bien conectado**: sí, síntesis/assembler respetan orden y report se arma correctamente.
- **Correcto de arriba a abajo (alcance actual)**: sí, dentro del alcance y contratos vigentes del repositorio.
