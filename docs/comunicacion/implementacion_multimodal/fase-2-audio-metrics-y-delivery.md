# Fase 2 — Métricas acústicas reales + evaluador de delivery real

## 1. Objetivo exacto de la fase

Implementar:

- extracción real de métricas acústicas desde audio,
- contrato real de `audio_features`,
- evaluador de delivery basado en métricas reales + evidencia.

Queda fuera:

- evaluación visual por frames,
- síntesis global final.

## 2. Por qué esta fase va en este orden

Depende de Fase 1 porque reutiliza audio extraído y pipeline de artefactos. Permite cerrar delivery real antes del coste alto multimodal visual.

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

- `backend/evaluacion/engine/communication_audio_metrics.py`
- `backend/evaluacion/engine/communication_delivery_evaluator.py`
- `backend/evaluacion/prompts/communication_delivery_evaluator_prompt.txt`

## 4. Cambios exactos por archivo

### `extractor.py`
- Hoy: métricas sintéticas (`speech_rate` por duración y `synthetic_pause`).
- Cambio: pipeline real de features acústicas.
- Riesgo: sensibilidad a calidad de audio.

### `communication_bundle_builder.py`
- Cambio: inyectar `audio_features_real` en bundle.
- Riesgo: coexistencia con transcript/visual en distinto nivel de madurez.

### `communication_evaluators.py`
- Cambio: reemplazar delivery placeholder por evaluator estructurado con métricas reales.
- Riesgo: alucinaciones de LLM sobre métricas no presentes.

### `communication_service.py`
- Cambio: introducir stage `audio_metrics_ready` real y retry policy de etapa.
- Riesgo: latencia en procesamiento acústico.

### `communication_models.py`
- Cambio: `CommunicationAudioFeaturesRealV1` con `raw_metrics` e `interpreted_metrics`.
- Riesgo: sobrecargar contrato con campos innecesarios.

### `communication_report_assembler.py`
- Cambio: block delivery con evidencias trazables a métricas reales.
- Riesgo: mantener legibilidad sin sobrecargar al usuario final.

## 5. Funciones, clases o módulos a crear o modificar

- `extract_pause_metrics(audio_track) -> PauseMetricsV1`
- `extract_speaking_rate(audio_track, transcript?) -> SpeakingRateMetricsV1`
- `extract_pitch_metrics(audio_track) -> PitchMetricsV1`
- `extract_energy_metrics(audio_track) -> EnergyMetricsV1`
- `build_audio_features_real(...) -> CommunicationAudioFeaturesRealV1`
- `evaluate_delivery_from_audio_metrics(input: CommunicationDeliveryEvaluatorInputV2) -> CommunicationDeliveryEvaluationV1`
- `validate_delivery_eval_schema(raw_llm_output) -> CommunicationDeliveryEvaluationV1`

## 6. Contratos de datos

### `CommunicationAudioFeaturesRealV1`
- `status`
- `raw_metrics`:
  - `pause_events[]`
  - `speech_rate_wpm`
  - `pitch_stats`
  - `energy_stats`
  - `voiced_ratio`
- `interpreted_metrics`:
  - `fluency_1_5`
  - `pause_control_1_5`
  - `expressiveness_1_5`
  - `stability_1_5`
- `quality_flags[]`
- `explanation`

### `CommunicationDeliveryEvaluationV1`
- `score_0_100`
- `subscores`
- `evidence_metrics[]`
- `observations[]`
- `recommendations[]`

Compatibilidad:

- mantener campo legacy mínimo durante transición si frontend/report depende de él.

## 7. Stages del job afectados

Stages fase 2:

- `audio_metrics_started`
- `audio_metrics_ready`
- `delivery_analysis_ready`

Orden:

`transcript_ready` (fase1) -> `audio_metrics_ready` -> `delivery_analysis_ready`.

## 8. Testing

### Unitarios
- cálculo de pausas/pitch/energy sobre fixtures controlados.
- normalización de métricas y quality flags.

### Integración
- pipeline con transcript real + audio metrics reales + delivery eval.

### Regresión
- shape de report y final_result sin romper contratos existentes.

### Contratos
- evaluator delivery no puede usar observaciones sin evidencia en `evidence_metrics`.

## 9. Riesgos de la fase

1. falsos positivos en métricas por ruido,
2. dependencia de librerías DSP y formatos de audio,
3. discrepancia entre métricas reales y narrativa LLM.

Mitigación:

- quality gates por señal,
- umbrales mínimos de fiabilidad,
- prompt + schema que obligue evidencias explícitas.

## 10. Criterio de aceptación

1. `audio_features` ya no es sintético en casos nominales,
2. evaluator delivery usa métricas reales y devuelve JSON estable,
3. report mantiene compatibilidad de consumo actual.

## 11. Qué NO entra en esta fase

- extracción y evaluación visual por frames,
- síntesis global final cross-evaluator,
- cambios en bridge Moodle/final_result.
