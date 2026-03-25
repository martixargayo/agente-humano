# Implementación multimodal real de `comunicacion` (plan técnico)

## Objetivo del cambio

Sustituir el motor placeholder actual de evaluación de `comunicacion` por un pipeline real multimodal que incorpore:

1. transcripción real del audio,
2. extracción real de métricas acústicas,
3. extracción real de frames del vídeo,
4. tres evaluadores especializados (contenido, delivery, visual),
5. una cuarta LLM de síntesis global,
6. ensamblado final del report compatible con frontend, exports y bridge Moodle existentes.

> Este plan **no implementa** cambios funcionales; define la ruta de implementación faseada.

## Diagnóstico del sistema actual

Hoy el flujo `comunicacion` ya tiene:

- bootstrap/captura/submit/evaluation/report/final_result completos;
- job engine con stages y report assembler;
- contratos tipados de evaluación y report;
- bridge Moodle contractual (`final_result_available -> final_result -> final_result_saved`) ya estabilizado.

Puntos placeholder actuales:

- transcript placeholder (`build_placeholder_transcript`);
- audio_features sintéticos (`build_placeholder_audio_features`);
- visual_features placeholder (`build_placeholder_visual_features`);
- evaluador visual explícitamente placeholder.

## Qué partes son placeholder hoy

- Dominio extractor: `backend/evaluacion/domains/communication/extractor.py`
- Bundle builder: `backend/evaluacion/engine/communication_bundle_builder.py`
- Evaluators: `backend/evaluacion/engine/communication_evaluators.py`
- Stages del job hoy reflejan placeholders (`visual_placeholder_ready`).

## Qué partes se mantendrán intactas

No tocar salvo necesidad extrema:

- contrato de entrega final en `backend/comunicacion_app/app.js` (bridge y ACK),
- secuencia `final_result_available -> final_result -> final_result_saved`,
- shape contractual de `final_result`,
- contrato de exports consumidos por frontend y embed,
- `backend/comunicacion_app/report_view.js` salvo consumo de campos nuevos compatibles.

## Arquitectura objetivo

Pipeline objetivo:

1. media extraction (audio + frames),
2. STT real (transcript con timestamps),
3. audio metrics reales (raw + interpretadas),
4. visual sampling real (manifest + batches),
5. evaluator contenido (LLM textual),
6. evaluator delivery (LLM sobre métricas),
7. evaluator visual (LLM multimodal),
8. LLM final de síntesis global,
9. assembler final de report compatible.

## Orden de implementación recomendado

- Fase 1: STT real + contenido real.
- Fase 2: audio metrics reales + delivery real.
- Fase 3: frames reales + visual real.
- Fase 4: síntesis global + ajuste de assembler/report.

## Criterios para no romper el sistema actual

1. Mantener contratos públicos de API de status/report.
2. Mantener shape de report esperado por frontend.
3. Mantener exports (`summary_html`, `report_json`, snapshot png).
4. Mantener contrato final_result/ACK ya cerrado con Moodle.
5. Añadir capacidad nueva por extensión de contratos (versionado), no por rotura.

## Mapa de módulos a tocar

Existentes a modificar:

- `backend/evaluacion/contracts/communication_models.py`
- `backend/evaluacion/domains/communication/extractor.py`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/engine/communication_evaluators.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/engine/communication_report_assembler.py`
- `backend/comunicacion/storage/models.py`
- `backend/comunicacion/storage/repository.py`

Nuevos recomendados:

- `backend/evaluacion/engine/communication_media_processing.py`
- `backend/evaluacion/engine/communication_stt.py`
- `backend/evaluacion/engine/communication_audio_metrics.py`
- `backend/evaluacion/engine/communication_frame_extractor.py`
- `backend/evaluacion/engine/communication_llm_clients.py`
- `backend/evaluacion/engine/communication_synthesis.py`
- prompts específicos de communication bajo `backend/evaluacion/prompts/`.

## Dependencias entre fases

- Fase 2 depende de artefacto de audio extraído en Fase 1.
- Fase 3 depende de estrategia de acceso a `video_ref` y política de temporales.
- Fase 4 depende de outputs estructurados de fases 1, 2 y 3.

## Riesgos globales

1. Dependencia externa (proveedor STT y modelo multimodal).
2. Latencia/coste en evaluación visual por frames.
3. Calidad de métricas acústicas en audios ruidosos.
4. Consistencia entre salidas de tres evaluadores especializados.
5. Riesgo de romper compatibilidad del report si no se versiona bien.

## Estrategia de testing global

1. Unit tests por extractor/evaluator/normalizer.
2. Integration tests por etapa del job.
3. Contract tests de report + exports + final_result (regresión).
4. Tests de degradación controlada por fallos parciales.
5. Tests de rendimiento (límites de frames/coste/latencia).

## Decisiones técnicas que hay que cerrar antes de implementar

1. Proveedor STT (cloud/API/modelo) y formato de salida oficial.
2. Estrategia de acceso a `video_ref` (download seguro/streaming/local cache).
3. Política de temporales (lifecycle, cleanup, tamaño máximo).
4. Política de cache de artefactos derivados (audio, transcript, frames, eval outputs).
5. Límites de frames por intento (fps, máximo absoluto, batching).
6. Límites de coste/token para LLMs (por etapa y global por evaluación).
7. Estrategia de retries por etapa (backoff, idempotencia).
8. Degradación controlada si falla una etapa (qué se marca `failed`, qué se permite `partial`).
9. Esquema de versionado de contratos (`v1` coexistente con `v2`).
10. Observabilidad mínima (trazas, hashes de artefactos, tiempos por stage).
