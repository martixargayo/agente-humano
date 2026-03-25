# Fase 2 — Attempt, recording y repositorio mínimo

## 1. Objetivo de la fase

Definir la primera capa de persistencia de negocio de `comunicacion`: `attempt`, `recording` y artefactos mínimos. Esta fase debe dejar cerrado el flujo exacto:

```text
bootstrap -> create attempt -> attach/upload recording
```

sin entrar todavía en la evaluación real del contenido.

## 2. Por qué va en este orden

Va después de Fase 1 porque ahora ya existe una sesión válida y una surface propia. Va antes de la UI completa y de la evaluación porque el resto del flujo necesita un identificador estable (`attempt_id`, `recording_id`) y un lugar claro donde guardar metadatos del vídeo sin meterlos en la sesión.

## 3. Archivos nuevos a crear

```text
backend/comunicacion/
  storage/
    __init__.py
    models.py
    repository.py
  services/
    attempt_service.py
    recording_service.py
```

Opcional si se prefiere segmentar contratos ya en esta fase:

```text
backend/comunicacion/models.py   # ampliar con modelos de attempt/upload
```

## 4. Archivos actuales a tocar

- `backend/comunicacion/api/router.py`
- `backend/comunicacion/models.py`
- `backend/comunicacion/services/session_service.py` solo para guardar referencias mínimas activas en sesión
- `backend/sessions/state.py` únicamente si hiciera falta encapsular helper de lectura/escritura neutral; no como refactor grande

## 5. Cambios exactos por archivo

### `backend/comunicacion/storage/models.py`
Definir exactamente:
- `AttemptRecord`
- `RecordingRecord`
- `DerivedArtifactRecord`
- enums/literals de estado mínimos

### `backend/comunicacion/storage/repository.py`
Definir un repositorio simple en memoria con operaciones mínimas:
- `create_attempt(...)`
- `get_attempt(...)`
- `save_attempt(...)`
- `attach_recording(...)`
- `get_recording(...)`
- `save_artifact(...)`
- `list_artifacts_for_recording(...)`

### `backend/comunicacion/services/attempt_service.py`
Definir:
- creación de attempt ligado a `user_id`, `session_id`, `context_id`
- validación de ownership
- transición de estado `draft` inicial

### `backend/comunicacion/services/recording_service.py`
Definir:
- attach de metadata de recording a un attempt existente
- validación de `attempt_id`
- persistencia de `video_ref`, `poster_frame_ref`, `duration_ms`, `mime_type`
- actualización del estado del attempt a `uploaded`

### `backend/comunicacion/api/router.py`
Añadir endpoints:
- `POST /attempts`
- `GET /attempts/{attempt_id}`
- `POST /attempts/{attempt_id}/upload`

## 6. Funciones / clases / modelos

### Entidades exactas

```python
class AttemptRecord(BaseModel):
    attempt_id: str
    user_id: str
    session_id: str
    flow_id: Literal['comunicacion']
    context_id: str
    status: Literal['draft', 'uploaded', 'submitted', 'completed', 'failed']
    recording_id: str | None = None
    latest_evaluation_id: str | None = None
    rerecord_count: int = 0
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
```

```python
class RecordingRecord(BaseModel):
    recording_id: str
    attempt_id: str
    user_id: str
    session_id: str
    mime_type: str
    duration_ms: int
    video_ref: str
    poster_frame_ref: str | None = None
    capture_meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
```

```python
class DerivedArtifactRecord(BaseModel):
    artifact_id: str
    recording_id: str
    kind: Literal['poster_frame', 'transcript', 'audio_features', 'visual_summary', 'bundle_snapshot']
    version: str
    storage_ref: str
    content_hash: str | None = None
    created_at: datetime
```

### Firmas de funciones

```python
def create_attempt(*, user_id: str, session_id: str) -> AttemptRecord: ...
```

```python
def attach_recording_to_attempt(
    *,
    user_id: str,
    session_id: str,
    attempt_id: str,
    mime_type: str,
    duration_ms: int,
    video_ref: str,
    poster_frame_ref: str | None = None,
    capture_meta: dict[str, Any] | None = None,
) -> RecordingRecord: ...
```

```python
def write_active_attempt_refs_to_session(
    *,
    state: SessionState,
    attempt_id: str | None = None,
    recording_id: str | None = None,
) -> None: ...
```

### Modelos API nuevos

```python
class CreateAttemptRequest(BaseModel):
    user_id: str
    session_id: str
```

```python
class CreateAttemptResponse(BaseModel):
    attempt_id: str
    status: Literal['draft']
    context_id: str
```

```python
class UploadRecordingRequest(BaseModel):
    user_id: str
    session_id: str
    mime_type: str
    duration_ms: int
    video_ref: str
    poster_frame_ref: str | None = None
    capture_meta: dict[str, Any] = Field(default_factory=dict)
```

## 7. Contratos JSON

### `POST /api/comunicacion/attempts`
```json
{
  "user_id": "iu_xxx",
  "session_id": "sess_xxx"
}
```

Respuesta:
```json
{
  "attempt_id": "att_01HXYZ",
  "status": "draft",
  "context_id": "baseline_current"
}
```

### `POST /api/comunicacion/attempts/{attempt_id}/upload`
```json
{
  "user_id": "iu_xxx",
  "session_id": "sess_xxx",
  "mime_type": "video/webm",
  "duration_ms": 92314,
  "video_ref": "storage://tmp/rec_01HXYZ/original.webm",
  "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg",
  "capture_meta": {
    "width": 1280,
    "height": 720,
    "audio_codec": "opus"
  }
}
```

Respuesta:
```json
{
  "attempt_id": "att_01HXYZ",
  "recording_id": "rec_01HXYZ",
  "status": "uploaded",
  "video_ref": "storage://tmp/rec_01HXYZ/original.webm",
  "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg"
}
```

## 8. Snippets de código orientativos

### Repositorio
```python
class InMemoryCommunicationRepository:
    def __init__(self) -> None:
        self._attempts: dict[str, AttemptRecord] = {}
        self._recordings: dict[str, RecordingRecord] = {}
        self._artifacts: dict[str, list[DerivedArtifactRecord]] = {}

    def create_attempt(self, record: AttemptRecord) -> AttemptRecord:
        self._attempts[record.attempt_id] = record
        return record
```

### Servicio create attempt
```python
def create_attempt(*, user_id: str, session_id: str) -> AttemptRecord:
    state = get_session_state(user_id=user_id, session_id=session_id)
    ensure_session_surface(state=state, surface='comunicacion')
    bound_context = ensure_communication_session_context(state=state)
    record = AttemptRecord(..., context_id=bound_context.context_id, status='draft')
    repository.create_attempt(record)
    write_active_attempt_refs_to_session(state=state, attempt_id=record.attempt_id)
    return record
```

### Servicio attach recording
```python
def attach_recording_to_attempt(...):
    attempt = repository.get_attempt(attempt_id)
    _assert_attempt_ownership(attempt, user_id=user_id, session_id=session_id)
    recording = RecordingRecord(...)
    repository.attach_recording(recording)
    attempt.recording_id = recording.recording_id
    attempt.status = 'uploaded'
    repository.save_attempt(attempt)
```

## 9. Tests recomendados

1. `backend/tests/test_comunicacion_attempt_repository.py`
   - crea attempt
   - lee attempt
   - persiste estado `draft`

2. `backend/tests/test_comunicacion_recording_repository.py`
   - adjunta recording a attempt existente
   - no permite attach a attempt inexistente
   - actualiza `attempt.status = uploaded`

3. `backend/tests/test_comunicacion_attempt_api.py`
   - `POST /attempts` devuelve `attempt_id`
   - `GET /attempts/{id}` respeta ownership
   - `POST /attempts/{id}/upload` devuelve `recording_id`

4. `backend/tests/test_comunicacion_session_refs.py`
   - solo guarda `active_attempt_id`, `last_recording_id`, `latest_evaluation_id` y `capture_status`
   - no guarda blob ni transcript en sesión

## 10. Riesgos de la fase

- meter demasiado estado en `SessionState`
- confundir `video_ref` con storage definitivo
- diseñar upload como multipart complejo antes de tiempo
- hacer depender el attach de la evaluación futura

## 11. Criterios de aceptación

- queda documentado qué se guarda en sesión y qué no
- `attempt_id` y `recording_id` tienen contrato estable
- existe repositorio mínimo de comunicación separado de negociación
- el flujo create attempt → attach recording está completamente especificado
- el diseño preserva `video_ref` para integración futura con report y Moodle

## 12. Qué NO entra aún en esta fase

- subida binaria real del archivo al storage definitivo
- transcript
- audio features
- `evaluation_id`
- report final
- embed final
