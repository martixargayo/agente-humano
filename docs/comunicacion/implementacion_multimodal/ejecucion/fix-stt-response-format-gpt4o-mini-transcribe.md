# Fix STT `response_format` para `gpt-4o-mini-transcribe`

## 1. Problema real detectado
En Railway / flujo directo de `comunicacion`, el polling devolvía:

- `pipeline_error:BadRequestError`
- Mensaje: `response_format 'verbose_json' is not compatible with model 'gpt-4o-mini-transcribe-api-ev3'. Use 'json' or 'text' instead.`

Esto indicaba que el pipeline sí alcanzaba la fase STT, pero la llamada al proveedor fallaba por formato incompatible.

## 2. Causa raíz
La capa STT (`OpenAiWhisperSttProvider`) hacía la llamada con:

- `model=gpt-4o-mini-transcribe` (modelo base en código)
- `response_format='verbose_json'`

En runtime, el modelo efectivo reportado por el proveedor (`...api-ev3`) rechazó `verbose_json`.

Además, ese error escapaba como excepción de SDK y podía tumbar el job completo con `pipeline_error`.

## 3. Decisión técnica aplicada
Se implementó **compatibilidad dual (opción B)**:

1. Intentar primero `response_format='verbose_json'`.
2. Si el proveedor devuelve error compatible con `unsupported_value` para `verbose_json`, reintentar automáticamente con `response_format='json'`.
3. Mapear errores de proveedor STT a `HTTPException` con detalle controlado (`stt_provider_request_failed`) para permitir degradación segura en bundle.

## 4. Cómo queda ahora la llamada STT
Flujo actual en provider:

- primer intento: `verbose_json`
- fallback automático: `json` ante incompatibilidad de formato
- error final (si falla): `HTTPException(502)` con metadata de proveedor/modelo/razón

## 5. Cómo se normaliza la respuesta
Se consolidó normalización en `normalize_openai_transcript(...)`:

- lee `text` y `language`
- si hay `segments`, los transforma a `CommunicationTranscriptSegment`
- si no hay `segments` pero hay texto, crea segmentación mínima compatible (segmento único 0–1000 ms)
- si no hay texto, devuelve error de transcript vacío

Se mantiene `normalize_openai_verbose_transcript(...)` como alias de compatibilidad.

## 6. Cómo se degrada si falla el proveedor
Al mapear errores STT a `HTTPException`, la capa bundle puede aplicar fallback controlado a transcript placeholder (sin crash bruto del pipeline), manteniendo compatibilidad operacional con el resto del flujo.

## 7. Tests ejecutados
- `python -m pytest backend/tests/test_communication_phase1_stt_and_content.py -q`
- `python -m pytest backend/tests/test_communication_phase2_audio_metrics_and_delivery.py -q`
- `python -m pytest backend/tests/test_communication_report_contract.py -q`
- `python -m pytest backend/tests/test_communication_report_exports_integrity.py -q`
- `python -m pytest backend/tests/test_communication_final_result_contract.py -q`

Además, se añadieron tests de cobertura para:
- normalización con payload `json` sin segments
- fallback automático `verbose_json -> json`
- mapeo de error de proveedor a `HTTPException` controlada
- degradación de bundle a transcript placeholder cuando STT falla

## 8. Qué NO se ha tocado
- `backend/comunicacion_app/*`
- bridge/embed/Moodle
- contrato `final_result`
- frontend
- arquitectura general

## 9. Veredicto de compatibilidad con report/final_result
El fix mantiene compatibilidad con:

- pipeline actual de evaluación
- ensamblado de report y exports (`report_json` + `summary_html`)
- contratos actuales de `CommunicationTranscriptRealV1`
- `final_result` (sin cambios de contrato ni de integración)

Incluso en respuestas STT menos ricas (sin segments), el pipeline sigue operativo vía segmentación mínima compatible.
