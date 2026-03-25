# Fase 3 — Frames reales + evaluador visual real

## 1. Objetivo exacto de la fase

Implementar:

- extracción real de frames del video,
- manifest temporal trazable,
- batching para evaluación multimodal,
- evaluador visual real con hallazgos temporales.

Queda fuera:

- síntesis global final.

## 2. Por qué esta fase va en este orden

Visual multimodal es la etapa con mayor coste/latencia. Debe entrar cuando ya existe transcript y delivery reales para reducir incertidumbre y permitir pruebas de regresión más fiables.

## 3. Archivos exactos a tocar

### Existentes a modificar

- `backend/evaluacion/domains/communication/extractor.py`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/engine/communication_evaluators.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/contracts/communication_models.py`
- `backend/evaluacion/engine/communication_report_assembler.py`
- `backend/comunicacion/storage/models.py`
- `backend/comunicacion/storage/repository.py`

### Nuevos recomendados

- `backend/evaluacion/engine/communication_frame_extractor.py`
- `backend/evaluacion/engine/communication_visual_evaluator.py`
- `backend/evaluacion/prompts/communication_visual_evaluator_prompt.txt`

## 4. Cambios exactos por archivo

### `extractor.py`
- Hoy: visual placeholder con score `None`.
- Cambio: generar `visual_features_real` y `frame_manifest`.
- Riesgo: volumen de artefactos y latencia.

### `communication_bundle_builder.py`
- Cambio: incluir refs a frames/batches en bundle.
- Riesgo: tamaño del bundle y serialización.

### `communication_evaluators.py`
- Cambio: reemplazar `evaluate_communication_visual_placeholder`.
- Riesgo: salida inconsistente por lotes.

### `communication_service.py`
- Cambio: stages `frames_ready`, `visual_analysis_ready`.
- Riesgo: timeout por lotes grandes.

### `communication_models.py`
- Cambio: modelos `FrameManifestV1`, `FrameBatchRef`, `CommunicationVisualEvaluationV1`.
- Riesgo: contrato demasiado acoplado a proveedor multimodal.

### `communication_report_assembler.py`
- Cambio: mapear hallazgos visuales temporales a timeline/recomendaciones.
- Riesgo: sobrecargar report con detalle técnico.

## 5. Funciones, clases o módulos a crear o modificar

- `extract_video_frames(video_ref, strategy) -> FrameManifestV1`
- `build_frame_batches(frame_manifest, *, max_frames_per_batch) -> list[FrameBatchRef]`
- `evaluate_visual_from_frames(input: CommunicationVisualEvaluatorInputV2) -> CommunicationVisualEvaluationV1`
- `merge_visual_batch_results(batch_results) -> CommunicationVisualEvaluationV1`
- `validate_visual_eval_schema(raw_llm_output) -> CommunicationVisualEvaluationV1`

## 6. Contratos de datos

### `FrameManifestV1`
- `video_ref`
- `sampling_policy`
- `frames[{frame_id,timestamp_ms,ref,width,height,quality}]`
- `windows[{start_ms,end_ms,frame_ids}]`

### `CommunicationVisualFeaturesRealV1`
- `status`
- `frame_manifest_ref`
- `coverage_stats`
- `quality_flags`

### `CommunicationVisualEvaluationV1`
- `score_0_100`
- `subscores`
- `temporal_findings[]`
- `observations[]`
- `recommendations[]`
- `evidence_frames[]`

## 7. Stages del job afectados

Stages fase 3:

- `frame_extraction_started`
- `frames_ready`
- `visual_analysis_started`
- `visual_analysis_ready`

Orden:

`extracting_media` -> `frames_ready` -> `visual_analysis_ready`.

## 8. Testing

### Unitarios
- frame sampler (frecuencia/límites),
- batch builder,
- consolidación de resultados por lotes.

### Integración
- job con visual real mockeado (multimodal provider fake) y manifest persistido.

### Regresión
- report compatible con frontend,
- exports/final_result sin cambios contractuales.

### Contratos
- cada hallazgo visual debe mantener referencia temporal (`start_ms/end_ms` o `frame_ids`).

## 9. Riesgos de la fase

1. coste elevado por número de frames,
2. latencia y límites del modelo multimodal,
3. baja precisión en condiciones de iluminación/cámara deficientes.

Mitigación:

- límites estrictos de frames,
- muestreo adaptativo,
- fallback de cobertura insuficiente con flags explícitos.

## 10. Criterio de aceptación

1. se generan frames reales con manifest trazable,
2. evaluador visual produce JSON estructurado con evidencia temporal,
3. report incluye bloque visual real sin romper shape existente.

## 11. Qué NO entra en esta fase

- síntesis global final de las tres evaluaciones,
- rediseño de frontend,
- cambios en bridge final_result/Moodle.
