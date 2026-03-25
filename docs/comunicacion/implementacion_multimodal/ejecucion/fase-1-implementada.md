# Fase 1 implementada — STT real + contenido real

## 1. Objetivo real de la fase

Reemplazar el transcript placeholder en el flujo nominal por un transcript real (cuando hay media accesible y proveedor STT disponible) y hacer que la evaluación de contenido consuma ese transcript real.

## 2. Archivos creados/modificados

### Creados

- `backend/evaluacion/engine/communication_media_processing.py`
- `backend/evaluacion/engine/communication_stt.py`
- `backend/evaluacion/engine/communication_content_evaluator.py`
- `backend/tests/test_communication_phase1_stt_and_content.py`
- `docs/comunicacion/implementacion_multimodal/ejecucion/fase-1-implementada.md`

### Modificados

- `backend/evaluacion/domains/communication/extractor.py`
- `backend/evaluacion/domains/communication/__init__.py`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/engine/communication_evaluators.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/contracts/communication_models.py`
- `backend/comunicacion/storage/models.py`
- `backend/comunicacion/storage/repository.py`
- `backend/evaluacion/engine/communication_report_assembler.py`
- `backend/tests/test_communication_bundle_builder.py`
- `backend/tests/test_communication_status_api.py`

## 3. Proveedor STT elegido y por qué

Se implementó un adaptador de proveedor STT con backend real principal:

- `OpenAiWhisperSttProvider` (API de OpenAI, formato `verbose_json` con timestamps).

Razones:

1. salida estructurada con segmentación temporal apta para timeline/evidencias,
2. integración directa con contratos tipados del repo,
3. encapsulación en adaptador mockeable para tests.

Además:

- `MockWordTimedSttProvider` queda disponible para entornos de test sin credenciales.

## 4. Cómo se extrae el audio

Se implementó extracción real mediante `ffmpeg`:

1. resolver media local (`resolve_recording_media_source`),
2. extraer pista mono 16k (`extract_audio_track`),
3. generar artefacto de audio temporal WAV para STT.

## 5. Cómo se genera el transcript real

Flujo:

1. `transcribe_audio(...)` resuelve proveedor STT,
2. proveedor genera transcript real,
3. normalización al contrato `CommunicationTranscriptRealV1`,
4. segmentación con `start_ms/end_ms/text`.

Se añadió normalizador explícito para respuesta `verbose_json` de OpenAI:

- `normalize_openai_verbose_transcript(...)`.

## 6. Cómo cambia el bundle

`build_communication_feedback_input_bundle(...)` ahora:

1. intenta `build_real_transcript(...)`,
2. si falla por condiciones de entorno/media, cae a `build_placeholder_transcript(...)`,
3. mantiene audio/visual placeholders (fuera de Fase 1).

Resultado:

- coexistencia compatible entre transcript real y placeholder.

## 7. Cómo cambia el evaluador de contenido

`evaluate_communication_content(...)` delega en:

- `evaluate_content_from_transcript(...)`

que usa `full_text`, segmentos y metadatos del transcript para producir salida estructurada estable:

- score,
- fortalezas/debilidades,
- recomendaciones,
- evidencia por segmento.

## 8. Stages reales añadidos

Se incorporaron stages de Fase 1 en `communication_service` / contratos:

- `extracting_media`
- `transcription_started`
- `transcript_ready`
- `content_analysis_ready`

Se mantienen stages existentes para compatibilidad del pipeline actual.

## 9. Tests ejecutados

Tests principales de esta fase:

- `backend/tests/test_communication_phase1_stt_and_content.py`
- `backend/tests/test_communication_bundle_builder.py`
- `backend/tests/test_communication_status_api.py`
- `backend/tests/test_communication_report_contract.py`
- `backend/tests/test_communication_final_result_contract.py`

## 10. Qué NO se ha implementado todavía

- métricas acústicas reales y evaluator delivery real (Fase 2),
- extracción real de frames y evaluator visual real (Fase 3),
- síntesis global final (Fase 4),
- cambios de contrato en `final_result`, exports o bridge Moodle.

## 11. Qué queda preparado para fase 2

Queda lista la base para extender:

1. artefactos derivados en storage (`audio_track`, `transcript_real`),
2. stages de job más granulares,
3. contrato real de transcript ya integrado en bundle/report,
4. adaptador de proveedor STT reusable para evolución multimodal.
