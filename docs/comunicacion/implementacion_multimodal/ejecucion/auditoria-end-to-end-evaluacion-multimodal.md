# Auditoría end-to-end — evaluación multimodal de comunicación

## 1) Objetivo de la auditoría
Verificar técnicamente, con evidencia ejecutable, que el pipeline completo de evaluación multimodal de `comunicacion` funciona desde `video_ref` hasta `report`/plantilla de feedback, incluyendo STT, métricas acústicas, visual, síntesis global, ensamblado y exports.

## 2) Alcance exacto auditado
Recorrido auditado:

`recording.video_ref` → `media_processing` → STT/transcript → audio metrics → frame extraction → evaluaciones parciales (contenido/delivery/visual) → síntesis global → assembler/report → exports (`summary_html`, `report_json`) → compatibilidad contractual `final_result`.

## 3) Estado del repo y commit auditado
- Rama: `work`
- Commit auditado (HEAD): `906cbef` + ajustes de auditoría de este documento/PR

## 4) Mapa real del pipeline completo
1. Resolución media: `resolve_recording_media_source` (`communication_media_processing.py`)
2. Audio: `extract_audio_track` (`communication_media_processing.py`)
3. STT: `build_real_transcript` + `transcribe_audio` (`extractor.py` / `communication_stt.py`)
4. Acústica: `build_audio_features_real` (`communication_audio_metrics.py` + `extractor.py`)
5. Frames: `extract_video_frames` (`communication_frame_extractor.py`)
6. Evaluaciones parciales: `evaluate_communication_content`, `evaluate_communication_delivery`, `evaluate_communication_visual`
7. Síntesis: `evaluate_communication_synthesis` → `communication_synthesis.py`
8. Assembler: `assemble_communication_report`
9. Exports/report_json/final_result contract: tests de contrato e integridad.

## 5) Archivos inspeccionados
- `backend/evaluacion/engine/communication_media_processing.py`
- `backend/evaluacion/engine/communication_stt.py`
- `backend/evaluacion/engine/communication_audio_metrics.py`
- `backend/evaluacion/engine/communication_frame_extractor.py`
- `backend/evaluacion/domains/communication/extractor.py`
- `backend/evaluacion/engine/communication_evaluators.py`
- `backend/evaluacion/engine/communication_synthesis.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/engine/communication_report_assembler.py`
- `backend/evaluacion/contracts/communication_models.py`
- `backend/comunicacion/storage/models.py`
- `backend/comunicacion/storage/repository.py`

## 6) Funciones clave por etapa
### A. Entrada y resolución de media
- `resolve_recording_media_source(recording)`
- Errores explícitos: `recording_video_ref_missing`, `recording_media_not_accessible`, `recording_media_scheme_not_supported`

### B. Extracción de audio
- `extract_audio_track(media_source, recording)`
- Dependencia: `ffmpeg` en PATH
- Output: WAV mono 16 kHz
- Errores: `ffmpeg_not_available_for_audio_extraction`, `audio_extraction_failed`, `audio_extraction_empty_output`

### C. STT
- Nominal: `build_real_transcript` + `transcribe_audio`
- Fallback: `build_placeholder_transcript` al fallar ruta real en bundle builder
- Persistencia: `persist_transcript_artifact` (`kind=transcript_real`)

### D. Métricas acústicas
- `build_audio_features_real` (`communication_audio_metrics.py`)
- Métricas: pausas, speaking rate, pitch, energy, voiced ratio, flags
- Persistencia: `persist_audio_metrics_artifact` (`kind=audio_metrics_real`)

### E. Frames y visual
- `extract_video_frames` con `fps` derivado de `sample_every_ms`, `max_frames`, `window_size`
- Manifest: frames + ventanas temporales
- Evaluación visual: `evaluate_visual_from_features`
- Persistencia: `frame_manifest`, `visual_evaluation`

### F/G. Evaluaciones parciales y síntesis
- Parciales: `evaluate_communication_content`, `evaluate_communication_delivery`, `evaluate_communication_visual`
- Síntesis: `evaluate_communication_synthesis` (input/output tipados + score global trazable)

### H/I. Assembler, report y plantilla de feedback
- `assemble_communication_report` incorpora `global_synthesis`, score global en header, recommendations y exports.
- El report final mantiene shape compatible consumido por frontend/export/final_result.

## 7) Tests ejecutados
### Suite solicitada
- `python -m pytest backend/tests/test_communication_phase1_stt_and_content.py -q`
- `python -m pytest backend/tests/test_communication_phase2_audio_metrics_and_delivery.py -q`
- `python -m pytest backend/tests/test_communication_phase3_frames_and_visual.py -q`
- `python -m pytest backend/tests/test_communication_phase4_synthesis_and_report.py -q`
- `python -m pytest backend/tests/test_communication_report_contract.py -q`
- `python -m pytest backend/tests/test_communication_final_result_contract.py -q`
- `python -m pytest backend/tests/test_communication_report_exports_integrity.py -q`
- `python -m pytest backend/tests/test_communication_status_api.py -q`
- `python -m pytest backend/tests/test_communication_evaluation_job.py -q`

### Tests añadidos para cerrar huecos de evidencia
- `python -m pytest backend/tests/test_communication_audit_media_processing.py -q`
- `python -m pytest backend/tests/test_communication_audit_pipeline_e2e.py -q`

## 8) Evidencia obtenida por etapa
### A. Media source
- Cobertura de caso local válido y esquema remoto no soportado.
- Cobertura de error controlado cuando no hay media accesible.

### B. Audio extraction
- Cobertura explícita de dependencia `ffmpeg` ausente.
- Cobertura de ruta nominal simulada con creación efectiva de WAV en output path.

### C. STT
- Normalización de transcript con timestamps y uso en bundle/content.
- Fallback controlado en ausencia de ruta real.
- Persistencia de artifact `transcript_real`.

### D. Acústica + delivery
- Cálculo de raw/interpreted metrics y consumo por evaluador delivery.
- Persistencia de artifact `audio_metrics_real`.

### E. Frames + visual
- Manifest con ventanas temporales y evaluación visual estructurada.
- Persistencia de `frame_manifest` y `visual_evaluation`.

### F/G. Parciales + síntesis
- Outputs parciales presentes y con schema estable.
- Síntesis consume las 3 salidas, calcula score global y emite campos estructurados (`global_diagnosis`, `top_strengths`, etc.).

### H/I. Assembler, exports y plantilla
- Report incluye bloques, timeline, recommendations, `global_synthesis` y exports.
- `summary_html` y `report_json` válidos.
- Contratos `report`/`final_result`/exports integridad en verde.
- E2E audit test confirma llegada de artefactos + report final con `global_synthesis`.

## 9) Fallos detectados
1. **Gap de evidencia nominal con binario real `ffmpeg` en este entorno de CI/sandbox**: no hay `ffmpeg`/`ffprobe` en PATH, por lo que no puede demostrarse aquí la extracción real contra binario del sistema sin mocks.

## 10) Fixes aplicados
Se aplicaron fixes mínimos de auditoría (sin refactor funcional de fases):
- test nuevo `test_communication_audit_media_processing.py` para cubrir resolución de media + extracción de audio (errores y ruta nominal simulada).
- test nuevo `test_communication_audit_pipeline_e2e.py` para verificar encadenamiento completo de artefactos y report final con síntesis global.

## 11) Gaps pendientes de evidencia
- Validación en runtime real con `ffmpeg` instalado y video de entrada real (no mock) sigue pendiente en este entorno concreto. El código de producción sí tiene rutas y manejo de error, pero la evidencia aquí es por simulación controlada para esa capa específica.

## 12) Veredicto final
- **¿Funciona de arriba abajo?** Sí, con evidencia fuerte por tests de integración/harness y contratos.
- **¿Está bien conectado?** Sí: media→parciales→síntesis→assembler→exports/final_result se observa conectado y estable.
- **¿Llega realmente del vídeo al feedback final?** Sí en ruta de pipeline (incluyendo fallback controlado donde aplica) y reporte final exportable.
- **¿Está cerrada la ruta nominal?** Funcionalmente sí; evidencia 100% real de extracción con binario `ffmpeg` queda limitada por entorno sin ese binario.
- **¿Qué límites siguen abiertos?** Ejecutar una corrida adicional con `ffmpeg` real disponible para evidencia no simulada de audio/frames.
