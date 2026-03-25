# Fase 1 — STT real + evaluador de contenido real

## 1. Objetivo exacto de la fase

Implementar:

- extracción real de audio desde `video_ref`,
- transcripción real con timestamps,
- reemplazo de transcript placeholder en el bundle,
- evaluador de contenido basado en transcript real.

Queda fuera en esta fase:

- métricas acústicas reales avanzadas para delivery,
- análisis visual por frames,
- LLM final de síntesis global.

## 2. Por qué esta fase va en este orden

El transcript real es dependencia directa del análisis de contenido y base para futuras fases (delivery/visual pueden complementar, pero contenido textual es el primer reemplazo de placeholder con mayor impacto funcional y menor complejidad que visual).

## 3. Archivos exactos a tocar

### Existentes a modificar

- `backend/evaluacion/domains/communication/extractor.py`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/engine/communication_evaluators.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/contracts/communication_models.py`
- `backend/comunicacion/storage/models.py`
- `backend/comunicacion/storage/repository.py`
- `backend/evaluacion/engine/communication_report_assembler.py` (ajustes mínimos de consumo)

### Nuevos recomendados

- `backend/evaluacion/engine/communication_media_processing.py`
- `backend/evaluacion/engine/communication_stt.py`
- `backend/evaluacion/engine/communication_content_evaluator.py`
- `backend/evaluacion/prompts/communication_content_evaluator_prompt.txt`

## 4. Cambios exactos por archivo

### `extractor.py`
- Hoy: builders placeholder.
- Problema: no existe transcript real.
- Cambio: mover lógica placeholder a fallback explícito y crear builders reales (`build_real_transcript_from_audio`).
- Contratos afectados: transcript placeholder -> transcript real versionado.
- Riesgo: latencia/fallos de STT.

### `communication_bundle_builder.py`
- Hoy: compone bundle con placeholders.
- Cambio: componer bundle con transcript real + metadata de calidad; mantener audio/visual placeholder temporales.
- Riesgo: dependencia de artefactos externos no disponibles.

### `communication_evaluators.py`
- Hoy: contenido heurístico fijo.
- Cambio: reemplazar `evaluate_communication_content(...)` por llamada a evaluator LLM textual con JSON estricto.
- Riesgo: respuestas no válidas de LLM.

### `communication_service.py`
- Hoy: stages `extracting -> transcript_ready` simulados.
- Cambio: stage real de STT, persistencia de transcript y manejo de retries.
- Riesgo: timeouts y jobs colgados.

### `communication_models.py`
- Cambio: añadir `CommunicationTranscriptRealV1` y coexistencia con `CommunicationTranscriptPlaceholder`.
- Riesgo: ruptura de validaciones si no se versiona.

### `storage/models.py` + `repository.py`
- Cambio: nuevos artifact kinds (`audio_track`, `transcript_real`).
- Riesgo: crecimiento de storage temporal y limpieza incompleta.

### `communication_report_assembler.py`
- Cambio mínimo: aprovechar segmentos reales para timeline y evidencias de contenido.
- Riesgo: mantener compatibilidad de shape report.

## 5. Funciones, clases o módulos a crear o modificar

- `extract_audio_track(video_ref, *, temp_dir) -> AudioTrackArtifact`
- `transcribe_audio(audio_artifact, *, language_hint='es') -> CommunicationTranscriptRealV1`
- `persist_transcript_artifact(evaluation_id, transcript)`
- `evaluate_content_from_transcript(input: CommunicationContentEvaluatorInputV2) -> CommunicationContentEvaluationV1`
- `validate_content_eval_schema(raw_llm_output) -> CommunicationContentEvaluationV1`
- `fallback_to_transcript_placeholder_on_failure(...)` (degradación controlada opcional)

## 6. Contratos de datos

Nuevos/extendidos:

- `CommunicationTranscriptRealV1`:
  - `status`, `provider`, `language`, `full_text`,
  - `segments[{start_ms,end_ms,text,confidence}]`,
  - `confidence_global`, `explanation`.

- `CommunicationContentEvaluatorInputV2`:
  - `evaluation_id`, `domain_context`, `transcript_real`, `recording_meta`.

- `CommunicationContentEvaluationV1`:
  - `score_0_100`, `strengths[]`, `weaknesses[]`,
  - `evidence_segments[]`, `recommendations[]`, `summary`.

Coexistencia:

- mantener modelo placeholder para fallback controlado durante transición.

## 7. Stages del job afectados

Propuesta fase 1:

- `extracting_media`
- `transcription_started`
- `transcript_ready`
- `content_analysis_ready`
- (stages actuales delivery/visual pueden quedar en placeholder temporal)

Dependencias:

- `content_analysis_ready` depende de `transcript_ready`.

## 8. Testing

### Unitarios
- audio extraction helper (resuelve/valida media source).
- parser/normalizer de transcript.
- schema validation del evaluator de contenido.

### Integración
- job end-to-end con transcript real mockeado.
- persistencia/lectura de artefactos transcript.

### Regresión
- report shape actual intacto.
- final_result contract intacto.

### Contratos de salida
- contenido devuelve JSON estable, no texto libre.

## 9. Riesgos de la fase

1. STT no determinista.
2. Timeouts en audios largos.
3. Fallos de acceso a `video_ref`.
4. Coste variable por duración.

Mitigación:

- retries acotados por etapa,
- límites de duración,
- fallback controlado con marca explícita de degradación.

## 10. Criterio de aceptación

La fase se considera terminada cuando:

1. el bundle contiene transcript real en casos nominales,
2. contenido se evalúa desde transcript real con JSON válido,
3. report mantiene shape compatible actual,
4. tests de regresión de report/final_result pasan sin cambios contractuales.

## 11. Qué NO entra en esta fase

- extracción acústica completa real para delivery,
- extracción de frames y análisis visual multimodal,
- LLM final de síntesis global,
- cambios de contrato en bridge Moodle/final_result.
