# Diagnóstico forense: Railway directo (`/comunicacion` y `/comunicacion/comunicacion`) en modo degradado / placeholder

## 1) Objetivo del diagnóstico

Determinar por qué una ejecución real de `comunicacion` en Railway (entrando directamente por URL pública, sin Moodle ni iframe) termina con evaluación degradada/placeholder, aunque el pipeline multimodal (STT, audio, frames, síntesis y report) exista en código.

Alcance:
- Trazar el flujo real front + backend.
- Verificar compatibilidad del `video_ref` real observado (`client-temp://...`).
- Ubicar el primer punto de degradación y sus efectos en contenido/delivery/visual.
- Comparar comportamiento real vs cobertura de tests.

---

## 2) Entorno exacto analizado

- Repositorio: `/workspace/agente-humano`
- Rama: `work`
- Fecha de análisis: 2026-03-25 (UTC)
- Contexto de ejecución objetivo del caso: acceso público directo a Railway
  - `/comunicacion`
  - `/comunicacion/comunicacion`
- Sin Moodle, sin iframe, sin bridge de parent container.

---

## 3) Evidencia primaria del caso real (aportada)

Resultado observado (resumen):
- Se genera `recording_id` (`rec_8494589bf5f9`).
- `video_ref` final en informe: `client-temp://sess_oW5tF7Vt1jJ16jHcnbTCk-NY/att_3a55f473abfc/1774436174353.webm`.
- Contenido: 0 palabras, 1 segmento, proveedor STT desconocido.
- Delivery: métricas acústicas placeholders.
- Visual: sin frame manifest real.
- Score global: 53/100.

Este patrón coincide exactamente con el camino de fallback explícito del código y con pruebas reproducidas localmente.

---

## 4) Reconstrucción exacta del flujo real

### 4.1 Entrada por rutas públicas

Las rutas `/comunicacion`, `/comunicacion/`, `/comunicacion/comunicacion` y `/comunicacion/comunicacion/` sirven el mismo `index.html` y los mismos assets (`app.js`, `report_view.js`, `styles.css`). No hay un pipeline distinto entre ambas rutas: cambia sólo el `public_slug` resuelto.  
Por tanto, **no hay evidencia de divergencia funcional relevante entre esas dos URLs**.

### 4.2 Captura y registro en frontend

En `backend/comunicacion_app/app.js`, al registrar metadata de grabación, **no se sube binario de vídeo al backend**; se envía únicamente metadata y un `video_ref` temporal generado por cliente:

- `deriveTemporaryVideoRef()` construye `client-temp://{session_id}/{attempt_id}/{timestamp}.webm|mp4`.
- `registerRecordingMetadata()` hace POST a `/api/comunicacion/attempts/{attempt_id}/upload` con ese `video_ref` y `capture_meta.provisional_client_ref=true`.

Esto explica por qué en el informe aparece un `video_ref` tipo `client-temp://...`: es exactamente el valor persistido del lado cliente.

### 4.3 Persistencia backend de `video_ref`

`attach_recording_to_attempt(...)` en `backend/comunicacion/services/recording_service.py` valida que `video_ref` no esté vacío, pero **no valida esquema** ni accesibilidad real del recurso. El valor queda persistido tal cual en `RecordingRecord.video_ref`.

### 4.4 Resolución de media para pipeline

El pipeline (`build_communication_feedback_input_bundle`) intenta preparar artefactos reales llamando `prepare_media_artifacts(recording)`, que internamente invoca `resolve_recording_media_source(recording)`.

Regla crítica actual en `backend/evaluacion/engine/communication_media_processing.py`:
- Soporta sólo refs con esquema vacío (ruta local) o `file://`.
- Requiere que el path exista en filesystem.
- Cualquier otro esquema (incluyendo `client-temp://`) => `HTTPException 409 recording_media_scheme_not_supported`.

### 4.5 Punto exacto donde arranca la degradación

Cuando `prepare_media_artifacts(...)` lanza excepción por esquema no soportado, `build_communication_feedback_input_bundle(...)` captura `HTTPException` y fuerza:
- `audio_track = None`
- `frame_manifest = None`

Después intenta transcript/audio/visual “reales” por rutas alternativas que vuelven a depender de `resolve_recording_media_source`; vuelven a fallar y cada rama cae a su placeholder:
- transcript: `build_placeholder_transcript`
- audio: `build_placeholder_audio_features`
- visual: `build_placeholder_visual_features`

### 4.6 Correspondencia 1:1 con tu resultado observado

Con esos placeholders:
- Contenido evalúa `full_text=''` => `0 palabras`, `1 segmento` placeholder y detalle `Proveedor STT: desconocido.`
- Delivery produce score base 52 con mensaje “No hay métricas acústicas reales...”
- Visual produce score base 50 con “No hay frame manifest real...”
- Síntesis ponderada sobre 55/52/50 da 53 global.

Es exactamente el mismo patrón textual y numérico de tu ejecución real en Railway.

---

## 5) Causas detectadas

## Causa raíz principal (confirmada)

**El flujo público directo actual sólo registra metadata y un `video_ref` temporal de cliente (`client-temp://...`), pero no deja el vídeo en una ubicación resoluble por el backend (ruta local existente o URL ingestada a local).**

Como el resolver de media backend no soporta `client-temp://`, no hay acceso a vídeo real para:
- extraer audio,
- transcribir,
- calcular métricas acústicas,
- extraer frames.

El sistema cae entonces a placeholders de forma controlada.

## Causas contribuyentes

1. Contrato upload permisivo: acepta cualquier `video_ref` no vacío.
2. Falta de etapa de persistencia/ingesta de blob grabado en flujo público directo.
3. Resolver de media deliberadamente estricto (local/file únicamente).

---

## 6) Tests ejecutados

Comandos solicitados y estado:

- `python -m pytest backend/tests/test_communication_audit_media_processing.py -q` ✅
- `python -m pytest backend/tests/test_communication_audit_pipeline_e2e.py -q` ✅
- `python -m pytest backend/tests/test_communication_phase1_stt_and_content.py -q` ✅
- `python -m pytest backend/tests/test_communication_phase2_audio_metrics_and_delivery.py -q` ✅
- `python -m pytest backend/tests/test_communication_phase3_frames_and_visual.py -q` ✅
- `python -m pytest backend/tests/test_communication_phase4_synthesis_and_report.py -q` ✅
- `python -m pytest backend/tests/test_public_comunicacion_serving.py -q` ✅
- `python -m pytest backend/tests/test_communication_report_api.py -q` ✅
- `python -m pytest backend/tests/test_communication_status_api.py -q` ✅

Además:
- `python -m pytest backend/tests/test_communication_railway_direct_placeholder_diagnosis.py -q` ✅

---

## 7) Tests nuevos añadidos y qué demuestran

Archivo nuevo: `backend/tests/test_communication_railway_direct_placeholder_diagnosis.py`

Prueba A:
- Verifica que `resolve_recording_media_source(...)` rechaza `client-temp://...` con `recording_media_scheme_not_supported` y `scheme=client-temp`.

Prueba B:
- Reproduce el flujo API de captura pública directa (upload metadata + submit) usando `video_ref=client-temp://...`.
- Verifica que el reporte final conserva ese `video_ref` y cae exactamente en degradación esperada:
  - contenido: `0 palabras, 1 segmentos` + STT desconocido,
  - delivery placeholder con ausencia de métricas acústicas reales,
  - visual placeholder por falta de frame manifest real.

Conclusión de cobertura nueva: **demuestra de forma ejecutable y determinista el mismo comportamiento de Railway reportado en el incidente**.

---

## 8) ¿Hubo fix?

No se aplicó fix funcional en este diagnóstico.

Motivo:
- El comportamiento observado es coherente con el diseño/implementación actual del flujo público directo.
- La causa no es un bug puntual en STT/audio/frames, sino un gap de ingestión de media (binario de vídeo no persistido en backend accesible).

Se priorizó diagnóstico forense con evidencia y trazabilidad completa.

---

## 9) Veredicto final

### Qué pasó exactamente

En Railway directo, la app generó y persistió un `video_ref` de cliente (`client-temp://...`) sin materializar un archivo de vídeo accesible para backend. El pipeline intentó procesar media real, no pudo resolver la fuente y cayó a placeholders en transcript/audio/visual. La síntesis final calculó 53/100 con esos inputs degradados.

### Por qué pasó

Porque el resolver backend de media sólo acepta rutas locales existentes o `file://`, y `client-temp://` no es resoluble por definición en servidor.

### Qué habría que hacer para salir de placeholder en Railway directo

Habilitar en el flujo público directo una persistencia real del vídeo previa al submit (por ejemplo: upload binario a storage/backend y `video_ref` final resoluble por backend, o ingesta server-side a ruta local temporal). Sin ese paso, el backend no puede ejecutar fases 1/2/3 reales.

---

## Respuestas directas a las 8 preguntas clave

1. **¿El problema real es que `video_ref = client-temp://...` no sirve para backend?**  
   Sí, confirmado.

2. **¿El flujo directo en Railway está incompleto respecto al pipeline multimodal esperado?**  
   Sí: falta persistencia/ingesta de media utilizable por backend.

3. **¿La grabación se está quedando solo en cliente o en referencia no resoluble?**  
   Sí: referencia temporal cliente no resoluble en backend.

4. **¿El backend necesita ruta local real o URL real descargable?**  
   En implementación actual, necesita path local existente o `file://` resoluble localmente.

5. **¿Hay bug real entre recording/upload y evaluación?**  
   Hay un gap funcional/contractual: upload acepta refs temporales no procesables por evaluación.

6. **¿`/comunicacion` y `/comunicacion/comunicacion` se comportan igual?**  
   Sí, mismo frontend y mismo pipeline backend; sólo cambia resolución de slug/contexto.

7. **¿Qué parte exacta falla primero?**  
   `resolve_recording_media_source(...)` al recibir `client-temp://...`.

8. **¿El sistema cae correctamente a placeholder o oculta algo más serio?**  
   Cae correctamente a placeholder controlado; no se observó crash, pero sí falta estructural de ingestión media.

