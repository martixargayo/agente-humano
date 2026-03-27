# Diagnóstico forense pipeline comunicación (2026-03-27)

Este documento resume evidencia reproducible del comportamiento real del pipeline de evaluación de comunicación, con foco en ramas LLM/fallback/placeholder y en el ensamblado del report final.

## Evidencia reproducible ejecutada

Comando principal ejecutado:

```bash
cd /workspace/agente-humano/backend && pytest -q \
  tests/test_communication_bundle_builder.py \
  tests/test_communication_visual_mode_regression.py \
  tests/test_communication_visual_fallback_mode.py \
  tests/test_communication_visual_pipeline_e2e_llm_mock.py \
  tests/test_communication_phase4_synthesis_and_report.py \
  tests/test_communication_railway_direct_placeholder_diagnosis.py \
  tests/test_communication_audit_pipeline_e2e.py \
  tests/test_communication_parallel_pipeline.py
```

Resultado: 19 tests OK y 1 FAIL (drift de expectativa textual en diagnóstico railway placeholder).

## Conclusión global

Estado global del sistema hoy: **pipeline mixto**.

- Puede ejecutar rutas **LLM reales** para contenido, audio, visual y síntesis global, pero dependen de flags/env y de disponibilidad de señales reales.
- En ejecución por defecto (sin flags) la **síntesis global cae por diseño en fallback** (`disabled_flag`).
- Cuando el `video_ref` es `client-temp://...` el backend no puede resolver el medio local y degrada transcript/audio/visual a placeholders.
- El report final conserva shape nuevo y puede parecer completo aunque la riqueza semántica venga de fallback/placeholders.

## Mapa técnico del pipeline

1. `communication_service._run_communication_evaluation_job`
   - Construye bundle multimodal.
   - Ejecuta ramas `contenido`, `delivery`, `visual` en paralelo (timeout configurable interno).
   - Ejecuta síntesis global.
   - Ensambla `UiCommunicationReportV1`.

2. `communication_bundle_builder.build_communication_feedback_input_bundle`
   - Resuelve intento/grabación/contexto.
   - Intenta preparar artefactos de media (audio track + frame manifest).
   - Transcript: intenta real; fallback a placeholder ante `HTTPException`.
   - Audio features: intenta real; fallback a placeholder ante `HTTPException`.
   - Visual features: intenta real; fallback a placeholder ante `HTTPException`.

3. Ramas evaluadoras
   - Contenido: `evaluate_content_from_transcript` (LLM opcional + fallback rule-based).
   - Delivery/audio: `evaluate_delivery_with_specialized_from_audio_metrics` (LLM opcional + fallback rule-based).
   - Visual: metadata heurística por defecto; LLM visual solo con `COMM_VISUAL_MODE=llm_v1` y `COMM_VISUAL_OPENAI_ENABLED=true`.

4. Síntesis global
   - `synthesize_global_communication_feedback`.
   - Por defecto fallback (`disabled_flag`) si `COMM_SYNTHESIS_OPENAI_ENABLED` no está activo.

5. Report
   - `assemble_communication_report` fusiona outputs de ramas + síntesis + bundle.
   - `header` y `recommendations` priorizan síntesis global cuando existe.
   - `placeholders` expone explicaciones del bundle (incluso cuando ciertas ramas estén ready).

## Flags/configs críticos

- `COMM_CONTENT_OPENAI_ENABLED`: habilita LLM de contenido.
- `COMM_CONTENT_OPENAI_MODEL`: modelo contenido (default `gpt-4.1-mini`).
- `COMM_AUDIO_OPENAI_ENABLED`: habilita LLM especializado de delivery.
- `COMM_AUDIO_OPENAI_MODEL`: modelo audio (default `gpt-4.1-mini`).
- `COMM_VISUAL_MODE`: `metadata` (default) o `llm_v1`.
- `COMM_VISUAL_OPENAI_ENABLED`: puerta adicional para rama visual LLM.
- `COMM_VISUAL_OPENAI_MODEL`, `_TIMEOUT_S`, `_MAX_RETRIES`.
- `COMM_SYNTHESIS_OPENAI_ENABLED`: habilita síntesis global LLM.
- `COMM_SYNTHESIS_OPENAI_MODEL`: modelo síntesis (default `gpt-4.1-mini`).
- `OPENAI_API_KEY`: requerido por rutas OpenAI (contenido/audio/visual/síntesis/STT OpenAI).
- `COMMUNICATION_STT_PROVIDER`: `mock`/`mock_word_timed_stt` o default OpenAI Whisper provider.

## Hallazgos clave

- El fallback de síntesis global observado (`mode=fallback`, `fallback_reason=disabled_flag`) es consistente con código y tests.
- `client-temp://` en `video_ref` fuerza degradación de extracción real (audio/frames), lo que empuja placeholders y reduce señal para feedback.
- La rama visual **sí puede ser real sin LLM** (metadata heurística sobre frame manifest real) y también puede usar LLM por lotes + síntesis visual final si se activa modo/flag.
- La plantilla final del report es robusta de contrato y siempre emite shape completo, incluso con señal pobre (riesgo de “aparente riqueza”).

