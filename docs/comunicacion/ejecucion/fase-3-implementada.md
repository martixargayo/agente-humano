# Comunicación — fase 3 implementada

## Objetivo real de la fase implementada

Esta fase convierte `backend/comunicacion_app/` en una app pública de captura mínima pero usable sobre los endpoints ya existentes de Fase 1 y Fase 2.

El flujo real implementado es:

```text
intro -> permissions -> preview -> recording -> review -> uploading
```

Además, quedan reservados placeholders limpios para `processing` y `report`, sin evaluación real ni submit funcional.

## Archivos creados

- `backend/tests/test_public_comunicacion_app_assets.py`
- `docs/comunicacion/ejecucion/fase-3-implementada.md`

## Archivos modificados

- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/report_view.js`
- `backend/comunicacion_app/styles.css`
- `backend/tests/test_public_comunicacion_serving.py`

## Estados de UI implementados

- `intro`
- `permissions`
- `preview`
- `recording`
- `review`
- `uploading`
- `error`

Y como placeholders reservados:
- `processing`
- `report`

## Funciones JS principales añadidas

- `bootstrapCommunicationSession()`
- `requestCapturePermissions()`
- `listCaptureDevices()`
- `openPreviewStream(...)`
- `stopPreviewStream()`
- `createAttempt()`
- `startRecording()`
- `stopRecording()`
- `resetRecordingReview()`
- `registerRecordingMetadata()`
- `transitionTo(screen)`
- `renderApp()`

## Cómo funciona el flujo real ya implementado

1. La app carga `/comunicacion`.
2. En `DOMContentLoaded` ejecuta bootstrap de sesión/contexto con `POST /api/comunicacion/sessions/bootstrap`.
3. El usuario entra en `intro` y pulsa “Empezar”.
4. En `permissions` puede pedir permisos y listar/cambiar dispositivos.
5. En `preview` abre la cámara y el micrófono con `getUserMedia`.
6. En `recording` graba localmente con `MediaRecorder` y muestra un indicador simple de tiempo.
7. En `review` reproduce el blob local con `<video controls>`.
8. Si decide registrar la grabación, la app crea un attempt con `POST /api/comunicacion/attempts` si aún no existe.
9. Después registra la metadata con `POST /api/comunicacion/attempts/{attempt_id}/upload`.
10. La app termina mostrando confirmación de “grabación registrada / fase preparada”, dejando el hueco de `processing` para Fase 4.

## Endpoints backend que consume esta fase

- `POST /api/comunicacion/sessions/bootstrap`
- `POST /api/comunicacion/attempts`
- `POST /api/comunicacion/attempts/{attempt_id}/upload`

No se consume todavía:
- `submit`
- polling de evaluación
- report final

## Cómo se maneja el `video_ref` provisional

Esta fase no intenta resolver storage binario real.

Cuando el usuario registra la grabación, la app genera una referencia provisional con esquema:

```text
client-temp://<session_id>/<attempt_id>/<timestamp>.<ext>
```

Esa referencia:
- representa una grabación local del cliente ya revisada,
- permite ejercitar el contrato actual de `/upload`,
- deja explícito en el código que el storage definitivo queda pendiente para fases posteriores,
- y evita fingir una solución de media persistente que aún no existe en backend.

## Qué queda preparado para la Fase 4

- un shell público con estados de captura ya operativos,
- una transición natural desde `uploading` a un futuro `submit`/`processing` real,
- placeholder de `report` para enchufar después el resultado del job,
- separación limpia entre la UI de captura y el renderer futuro.

## Qué NO se ha implementado aún

- submit real
- `evaluation_id`
- polling real
- transcript
- audio features
- visual analytics
- report final
- renderer real del informe
- snapshot PNG
- serialización HTML del informe
- `final_result`
- embed final
- Moodle/cuaderno
- storage binario real del vídeo

## Tests ejecutados

- `pytest -q backend/tests/test_public_comunicacion_app_assets.py backend/tests/test_public_comunicacion_serving.py backend/tests/test_comunicacion_bootstrap_api.py backend/tests/test_comunicacion_attempt_api.py backend/tests/test_comunicacion_attempt_repository.py backend/tests/test_comunicacion_recording_repository.py backend/tests/test_comunicacion_session_refs.py backend/tests/test_comunicacion_context_binding.py`
- `pytest -q backend/tests/test_public_interfaz_usuario_serving.py backend/tests/test_phase8_second_official_context.py -q`

## Riesgos o decisiones pendientes

- `MediaRecorder` y `getUserMedia` dependen del soporte real del navegador; los tests de esta fase son smoke/contract tests, no browser automation completa.
- `video_ref` sigue siendo provisional y deliberadamente no persistente.
- no se implementa aún `submit`, por lo que `processing` y `report` son placeholders explícitos.
- `report_view.js` queda como módulo placeholder limpio para no adelantar Fase 5.
