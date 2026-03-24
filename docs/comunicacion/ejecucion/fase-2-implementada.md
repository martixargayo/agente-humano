# Comunicación — fase 2 implementada

## Objetivo real de la fase implementada

Esta fase deja operativo el primer corte de persistencia de negocio de `comunicacion`:

```text
bootstrap -> create attempt -> get attempt -> attach/upload recording
```

Se implementa `attempt`, `recording`, repositorio mínimo en memoria, endpoints API de esta fase y refs ligeras de runtime en sesión. No se implementa evaluación, submit, report, renderer ni integración externa.

## Archivos creados

- `backend/comunicacion/storage/__init__.py`
- `backend/comunicacion/storage/models.py`
- `backend/comunicacion/storage/repository.py`
- `backend/comunicacion/services/attempt_service.py`
- `backend/comunicacion/services/recording_service.py`
- `backend/tests/test_comunicacion_attempt_api.py`
- `backend/tests/test_comunicacion_attempt_repository.py`
- `backend/tests/test_comunicacion_recording_repository.py`
- `backend/tests/test_comunicacion_session_refs.py`

## Archivos modificados

- `backend/comunicacion/api/router.py`
- `backend/comunicacion/models.py`
- `backend/comunicacion/services/__init__.py`
- `backend/comunicacion/services/session_service.py`

## Endpoints añadidos

### `POST /api/comunicacion/attempts`
Crea un `AttemptRecord` ligado a `user_id`, `session_id`, `flow_id='comunicacion'` y `context_id` del binding actual.

### `GET /api/comunicacion/attempts/{attempt_id}`
Lee el attempt y valida ownership por `user_id` y `session_id` vía query params.

### `POST /api/comunicacion/attempts/{attempt_id}/upload`
No realiza upload binario complejo. Registra metadata de una grabación ya disponible mediante `video_ref` + `poster_frame_ref` opcional + `capture_meta`.

## Modelos añadidos

### Persistencia
- `AttemptRecord`
- `RecordingRecord`
- `DerivedArtifactRecord`

### API
- `CreateAttemptRequest`
- `CreateAttemptResponse`
- `GetAttemptResponse`
- `UploadRecordingRequest`
- `UploadRecordingResponse`

## Servicios añadidos

### `attempt_service.py`
- `create_attempt(...)`
- `get_attempt(...)`
- validación de sesión existente, surface `comunicacion`, contexto bound y ownership del attempt

### `recording_service.py`
- `attach_recording_to_attempt(...)`
- validación de `attempt_id`, ownership, `mime_type`, `duration_ms`, `video_ref` y estado compatible del attempt
- transición de `attempt.status` de `draft` a `uploaded`

## Cambio exacto en sesión

Se añade un bloque mínimo `communication_runtime` dentro de `world_state`, exclusivamente para refs ligeras:
- `active_attempt_id`
- `last_recording_id`
- `latest_evaluation_id` (reservado para fases posteriores)
- `capture_status`

No se guardan blobs, base64, transcript ni artefactos pesados.

## Qué queda preparado para la Fase 3

- la UI podrá crear attempts y consultar attempts existentes,
- la UI podrá registrar una grabación ya disponible vía `video_ref`,
- el bootstrap ya devuelve `last_attempt_id` y `last_evaluation_id` a partir de las refs ligeras de sesión.

## Qué NO se ha implementado aún

- upload binario real definitivo
- submit
- `evaluation_id`
- transcript
- audio features
- visual analytics
- report
- renderer
- `final_result`
- embed final
- Moodle/cuaderno

## Tests ejecutados

- `pytest -q backend/tests/test_comunicacion_attempt_repository.py backend/tests/test_comunicacion_recording_repository.py backend/tests/test_comunicacion_attempt_api.py backend/tests/test_comunicacion_session_refs.py`
- `pytest -q backend/tests/test_public_comunicacion_serving.py backend/tests/test_comunicacion_bootstrap_api.py backend/tests/test_comunicacion_context_binding.py`
- `pytest -q backend/tests/test_public_interfaz_usuario_serving.py backend/tests/test_phase8_second_official_context.py -q`

## Riesgos o decisiones que siguen pendientes

- `video_ref` sigue siendo una referencia opaca; no hay storage binario definitivo.
- `DerivedArtifactRecord` queda preparado, pero todavía no participa en transcript ni features.
- la API de `GET /attempts/{id}` usa query params para ownership porque esta fase todavía no define auth ni envelope más sofisticado.
- no se ha introducido ningún contrato de evaluación ni `submit`, para mantener la fase estrictamente contenida.
