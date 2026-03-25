# 01 — Backend y rutas

## 1. Resumen ejecutivo

La propuesta backend más segura para `comunicacion` es una estructura de dominio nueva con cuatro capas pequeñas y explícitas:
1. `api/` para routing HTTP,
2. `services/` para coordinación de casos de uso,
3. `contexts/` para selección pública y binding de contexto,
4. `storage/` para entidades/repositorios de attempts y recordings.

El objetivo es copiar el patrón maduro de `backend/interfaz_usuario/` sin heredar su semántica de negociación por turnos. Los cambios transversales deben limitarse a:
- montar una nueva surface en `backend/api/app.py`,
- permitir una nueva surface en `backend/sessions/surface_scope.py`,
- y, de forma opcional/recomendada, reducir el sesgo a negociación en `export_session_envelope(...)`.

---

## 2. Árbol de carpetas definitivo recomendado

```text
backend/comunicacion/
  __init__.py
  api/
    __init__.py
    router.py
  models.py
  contexts/
    __init__.py
    models.py
    resolver.py
    public_mapping.py
    session_binding.py
    baseline_current/
      manifest.json
      presentation/
        presentation_config.json
      assets/
        activity_brief.json
        capture_policy.json
      evaluation/
        report_manifest.json
  services/
    __init__.py
    session_service.py
    attempt_service.py
    recording_service.py
    evaluation_service.py
  storage/
    __init__.py
    models.py
    repository.py
```

## 2.1 Justificación por archivo nuevo

### `backend/comunicacion/api/router.py`
**Responsabilidad**
- definir el `APIRouter(prefix="/api/comunicacion")`,
- mapear endpoints HTTP a servicios,
- aplicar validación Pydantic,
- mantener paridad estilística con `backend/interfaz_usuario/__init__.py`.

**Importaría**
- `fastapi.APIRouter`, `HTTPException`
- `backend/comunicacion/models.py`
- servicios de `backend/comunicacion/services/*`

**Hablaría con**
- `session_service`
- `attempt_service`
- `recording_service`
- `evaluation_service`

### `backend/comunicacion/models.py`
**Responsabilidad**
- agrupar contratos API de bootstrap, create attempt, upload, submit, status y report refs.

**Importaría**
- `pydantic.BaseModel`, `ConfigDict`, `Field`

**Hablaría con**
- router
- services

### `backend/comunicacion/services/session_service.py`
**Responsabilidad**
- bootstrap de sesión de comunicación,
- binding de surface y contexto,
- TTL de bootstrap/active,
- lectura de `presentation_config`.

**Referencias reales**
- `backend/interfaz_usuario/services.py::ensure_session`
- `backend/interfaz_usuario/services.py::finalize_session`

### `backend/comunicacion/services/attempt_service.py`
**Responsabilidad**
- crear `attempt_id`,
- consultar attempts,
- permitir rerecord mínima,
- validar ownership y estado.

### `backend/comunicacion/services/recording_service.py`
**Responsabilidad**
- registrar metadata de grabación subida,
- enlazar `recording_id` con `attempt_id`,
- almacenar refs persistidas,
- devolver poster/video ref/resumen técnico.

### `backend/comunicacion/services/evaluation_service.py`
**Responsabilidad**
- disparar creación de evaluación desde `attempt_id`,
- consultar status/report por `evaluation_id`,
- traducir estado interno de comunicación a respuestas API.

### `backend/comunicacion/contexts/models.py`
**Responsabilidad**
- equivalente de `backend/negociacion/contexts/models.py`, pero para:
  - `BoundCommunicationContext`
  - `ResolvedCommunicationContext`

### `backend/comunicacion/contexts/resolver.py`
**Responsabilidad**
- resolver contextos oficiales de comunicación,
- exponer `resolve_default_communication_context()`,
- listar contextos oficiales,
- mantener `flow_id = "comunicacion"`.

### `backend/comunicacion/contexts/public_mapping.py`
**Responsabilidad**
- resolver `public_slug` ↔ `context_id`.

### `backend/comunicacion/contexts/session_binding.py`
**Responsabilidad**
- fijar el contexto de comunicación en `world_state`,
- evitar reutilización conflictiva de sesión.

### `backend/comunicacion/storage/models.py`
**Responsabilidad**
- definir entidades persistibles mínimas:
  - `AttemptRecord`
  - `RecordingRecord`
  - `DerivedArtifactRecord`

### `backend/comunicacion/storage/repository.py`
**Responsabilidad**
- repositorio en memoria MVP para attempts/recordings/artefactos,
- API estilo simple similar al repo de `evaluacion/storage`.

---

## 3. Archivos actuales del repo que habría que tocar

| Archivo | Cambio propuesto | Obligatorio | Riesgo | Comentario |
|---|---|---:|---|---|
| `backend/api/app.py` | montar nueva app estática y nuevo router `comunicacion` | Sí | Bajo | Cambio acotado, siguiendo patrón de `/interfaz_usuario` |
| `backend/sessions/surface_scope.py` | añadir nueva surface `comunicacion` | Sí | Medio | Es el cambio transversal mínimo necesario para evitar contaminación de sesiones |
| `backend/sessions/state.py` | opcional: reducir sesgo de `export_session_envelope()` / `hydrate_session_state()` a negociación | Recomendado | Medio | No bloquearía MVP inicial si `comunicacion` no exporta envelope complejo |
| `docs/comunicacion/README.md` | enlazar nueva capa ejecutable | Sí | Nulo | documental |
| `backend/evaluacion/engine/service.py` | no tocar para MVP si se crea entrypoint paralelo en módulo nuevo | No | Medio | tocarlo pronto puede mezclar contratos demasiado pronto |
| `backend/evaluacion/api/router.py` | no tocar para MVP; preferible router específico en `backend/comunicacion/api/router.py` | No | Bajo | separación más limpia |
| `backend/interfaz_usuario_app/app.js` | no tocar para MVP de `comunicacion` | No | Alto | alto riesgo de regresión en negociación |

### 3.1 Cambio obligatorio mínimo recomendado sobre `SessionSurface`

**Decisión cerrada**: no hacer una refactorización masiva.

**Versión más pequeña y segura**:
```python
SessionSurface = Literal['optimizador', 'interfaz_usuario', 'comunicacion']
```

y ampliar:
```python
if value in {'optimizador', 'interfaz_usuario', 'comunicacion'}:
    return value
```

Nada más en esta fase. No introducir abstracciones nuevas ni enums si no hacen falta todavía.

---

## 4. Router exacto propuesto

## 4.1 `POST /api/comunicacion/sessions/bootstrap`

**Propósito**
- crear o rehidratar sesión pública de comunicación,
- fijar surface/contexto,
- devolver `presentation_config` + `capture_policy`.

**Request sugerido**
```json
{
  "user_id": null,
  "session_id": null,
  "context_id": null,
  "public_slug": null
}
```

**Response sugerida**
```json
{
  "user_id": "iu_xxx",
  "session_id": "sess_xxx",
  "session_bootstrap_state": "new",
  "existing_session": false,
  "context_id": "baseline_current",
  "public_slug": "comunicacion",
  "presentation_config": {
    "version": "1.0.0"
  },
  "capture_policy": {
    "video_required": true,
    "audio_required": true,
    "max_duration_seconds": 180,
    "allow_rerecord": true,
    "accepted_mime_types": ["video/webm", "video/mp4"]
  },
  "last_attempt_id": null,
  "last_evaluation_id": null
}
```

**Validaciones**
- `context_id` y `public_slug` no pueden entrar en conflicto.
- si la sesión ya existe con otro contexto de comunicación → `409 session_context_conflict`.
- si la sesión ya está ligada a otra surface → `409 session_surface_conflict`.

**Errores esperables**
- `404 unsupported_public_slug`
- `404 unsupported_context_id`
- `409 session_surface_conflict`
- `409 session_context_conflict`

**Función backend**
```python
def ensure_communication_session(...) -> dict[str, Any]
```

---

## 4.2 `POST /api/comunicacion/attempts`

**Propósito**
- crear un intento (`attempt_id`) para la sesión actual.

**Request sugerido**
```json
{
  "user_id": "iu_xxx",
  "session_id": "sess_xxx"
}
```

**Response sugerida**
```json
{
  "attempt_id": "att_xxx",
  "user_id": "iu_xxx",
  "session_id": "sess_xxx",
  "status": "draft",
  "rerecord_count": 0,
  "recording_id": null,
  "latest_evaluation_id": null,
  "created_at": "2026-03-23T00:00:00Z",
  "updated_at": "2026-03-23T00:00:00Z"
}
```

**Validaciones**
- sesión existente y ligada a surface `comunicacion`.
- opcional MVP: impedir múltiples attempts abiertos simultáneamente.

**Errores esperables**
- `404 session_not_found`
- `409 active_attempt_already_exists`

**Función backend**
```python
def create_attempt(*, user_id: str, session_id: str) -> AttemptRecord:
    ...
```

---

## 4.3 `POST /api/comunicacion/attempts/{attempt_id}/upload`

**Propósito**
- adjuntar metadata y referencia de la grabación subida al attempt.

**Decisión MVP recomendada**
- en MVP documental, tratar este endpoint como “registro de recording subida”, no definir todavía transporte binario definitivo.

**Request sugerido**
```json
{
  "user_id": "iu_xxx",
  "session_id": "sess_xxx",
  "mime_type": "video/webm",
  "duration_ms": 92314,
  "video_ref": "storage://tmp/original.webm",
  "poster_frame_ref": "storage://tmp/poster.jpg",
  "capture_meta": {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "audio_codec": "opus",
    "video_codec": "vp9"
  }
}
```

**Response sugerida**
```json
{
  "attempt_id": "att_xxx",
  "recording_id": "rec_xxx",
  "status": "uploaded",
  "recording": {
    "recording_id": "rec_xxx",
    "mime_type": "video/webm",
    "duration_ms": 92314,
    "video_ref": "storage://tmp/original.webm",
    "poster_frame_ref": "storage://tmp/poster.jpg"
  }
}
```

**Validaciones**
- `attempt_id` existe y pertenece a la sesión/usuario.
- `duration_ms > 0`.
- `mime_type` permitido por capture policy.
- attempt no está ya `submitted`.

**Errores esperables**
- `404 attempt_not_found`
- `409 attempt_already_submitted`
- `400 invalid_recording_metadata`

**Función backend**
```python
def attach_recording_to_attempt(
    *,
    user_id: str,
    session_id: str,
    attempt_id: str,
    video_ref: str,
    mime_type: str,
    duration_ms: int,
    poster_frame_ref: str | None,
    capture_meta: dict[str, Any] | None,
) -> RecordingRecord:
    ...
```

---

## 4.4 `POST /api/comunicacion/attempts/{attempt_id}/submit`

**Propósito**
- congelar el attempt y disparar evaluación.

**Request sugerido**
```json
{
  "user_id": "iu_xxx",
  "session_id": "sess_xxx"
}
```

**Response sugerida**
```json
{
  "attempt_id": "att_xxx",
  "evaluation_id": "eval_xxx",
  "status": "queued",
  "submitted_at": "2026-03-23T00:00:00Z"
}
```

**Validaciones**
- attempt existe,
- tiene `recording_id`,
- no fue enviado ya.

**Errores esperables**
- `404 attempt_not_found`
- `409 attempt_without_recording`
- `409 attempt_already_submitted`

**Función backend**
```python
def submit_attempt_for_evaluation(*, user_id: str, session_id: str, attempt_id: str) -> dict[str, Any]:
    ...
```

---

## 4.5 `GET /api/comunicacion/attempts/{attempt_id}`

**Propósito**
- consultar el estado actual del attempt.

**Response sugerida**
```json
{
  "attempt_id": "att_xxx",
  "status": "uploaded",
  "recording_id": "rec_xxx",
  "latest_evaluation_id": "eval_xxx",
  "rerecord_count": 0,
  "created_at": "...",
  "updated_at": "..."
}
```

**Función backend**
```python
def get_attempt(*, user_id: str, session_id: str, attempt_id: str) -> AttemptRecord:
    ...
```

---

## 4.6 `GET /api/comunicacion/evaluations/{evaluation_id}`

**Propósito**
- consultar estado del job de comunicación.

**Decisión recomendada**
- exponer shape similar a `EvaluationStatusResponse`, pero desde router propio.

**Función backend**
```python
def get_communication_evaluation_status(*, evaluation_id: str) -> dict[str, Any]:
    ...
```

---

## 4.7 `GET /api/comunicacion/evaluations/{evaluation_id}/report`

**Propósito**
- devolver `UiCommunicationReportV1`.

**Función backend**
```python
def get_communication_report(*, evaluation_id: str) -> UiCommunicationReportV1:
    ...
```

---

## 5. Firmas de funciones recomendadas

## 5.1 `session_service.py`

```python
from typing import Any


def ensure_communication_session(
    *,
    user_id: str | None,
    session_id: str | None,
    context_id: str | None = None,
    public_slug: str | None = None,
) -> dict[str, Any]:
    """Crea o rehidrata una sesión pública de comunicación, fija surface/contexto y devuelve bootstrap payload."""
```

**Side effects**
- puede crear sesión,
- fija `_session_surface`,
- fija `communication_context`,
- aplica TTL bootstrap/active.

## 5.2 `attempt_service.py`

```python
from comunicacion.storage.models import AttemptRecord


def create_attempt(*, user_id: str, session_id: str) -> AttemptRecord:
    """Crea un nuevo intento en estado draft para la sesión."""


def get_attempt(*, user_id: str, session_id: str, attempt_id: str) -> AttemptRecord:
    """Devuelve el intento validando ownership."""
```

## 5.3 `recording_service.py`

```python
from typing import Any
from comunicacion.storage.models import RecordingRecord


def attach_recording_to_attempt(
    *,
    user_id: str,
    session_id: str,
    attempt_id: str,
    video_ref: str,
    mime_type: str,
    duration_ms: int,
    poster_frame_ref: str | None = None,
    capture_meta: dict[str, Any] | None = None,
) -> RecordingRecord:
    """Registra metadata y refs de una grabación ya subida y la enlaza al attempt."""
```

## 5.4 `evaluation_service.py`

```python
from typing import Any


def submit_attempt_for_evaluation(*, user_id: str, session_id: str, attempt_id: str) -> dict[str, Any]:
    """Congela el attempt y crea el job de evaluación de comunicación."""


def get_communication_evaluation_status(*, evaluation_id: str) -> dict[str, Any]:
    """Devuelve estado del job de comunicación."""


def get_communication_report(*, evaluation_id: str):
    """Devuelve el report final ya ensamblado."""
```

---

## 6. Snippets de código orientativos

## 6.1 Estructura de APIRouter

```python
# backend/comunicacion/api/router.py
from fastapi import APIRouter

from comunicacion.models import (
    CommunicationBootstrapRequest,
    CommunicationBootstrapResponse,
    CreateAttemptRequest,
    CreateAttemptResponse,
)
from comunicacion.services import session_service, attempt_service

router = APIRouter(prefix="/api/comunicacion", tags=["comunicacion"])


@router.post("/sessions/bootstrap", response_model=CommunicationBootstrapResponse)
def bootstrap_session(payload: CommunicationBootstrapRequest) -> CommunicationBootstrapResponse:
    result = session_service.ensure_communication_session(
        user_id=payload.user_id,
        session_id=payload.session_id,
        context_id=payload.context_id,
        public_slug=payload.public_slug,
    )
    return CommunicationBootstrapResponse(**result)
```

## 6.2 Pattern de uso de locks

```python
from sessions.session_lock import acquire_session_execution_lock


def create_attempt(*, user_id: str, session_id: str) -> AttemptRecord:
    with acquire_session_execution_lock(user_id=user_id, session_id=session_id):
        state = get_session_state(user_id=user_id, session_id=session_id)
        ensure_session_surface(state=state, surface="comunicacion")
        # crear y persistir AttemptRecord
```

## 6.3 Pattern de binding de surface/contexto

```python
from sessions.surface_scope import ensure_session_surface
from comunicacion.contexts.session_binding import ensure_communication_session_context


def ensure_communication_session(...):
    state = get_session_state(user_id=normalized_user_id, session_id=normalized_session_id)
    ensure_session_surface(state=state, surface="comunicacion")
    bound_context = ensure_communication_session_context(state=state, requested_context_id=context_id)
```

---

## 7. Decisión sobre `SessionSurface` / `SessionEnvelope`

## 7.1 `SessionSurface`

**Decisión cerrada**
- ampliar el `Literal` actual a `comunicacion`.

**Qué tocaría**
- solo `backend/sessions/surface_scope.py`.

**Qué NO tocaría aún**
- no convertiría `SessionSurface` en enum/clase base ni introduciría un registro dinámico.

## 7.2 `SessionEnvelope`

**Propuesta recomendada (MVP)**
- no tocarlo de entrada si `comunicacion` no necesita export/import robusto de envelope en su primera iteración.

**Alternativa posible**
- hacer un cambio pequeño en `backend/sessions/state.py` para que `bindings.context` lea primero `communication_context` y, si no existe, `negotiation_context`, o almacenar `bindings.context` desde una clave seleccionada por `surface`.

**Riesgo**
- tocar demasiado pronto `export_session_envelope()` puede romper expectativas de tests y tooling legado de negociación.

**Recomendación**
- posponer la generalización del envelope salvo que el MVP de `comunicacion` necesite explícitamente exportación/rehidratación.

---

## 8. Recomendación final del bloque

El backend ejecutable de `comunicacion` debe empezar pequeño: router propio, services separados, repositorio simple de attempts/recordings y un único cambio transversal obligatorio (`SessionSurface`). Cualquier generalización mayor debe justificarse por necesidad real del MVP, no por elegancia arquitectónica.
