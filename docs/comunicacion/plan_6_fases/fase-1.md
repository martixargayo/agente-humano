# Fase 1 — Cimientos de arquitectura, surface y bootstrap

## 1. Objetivo de la fase

Construir el esqueleto técnico mínimo para que `comunicacion` exista como flujo de primera clase dentro de la repo sin implementar todavía captura, evaluación ni report completo. Esta fase debe dejar operativos, al menos a nivel de diseño implementable:
- el namespace `backend/comunicacion/`,
- el router `/api/comunicacion`,
- la surface pública `/comunicacion`,
- los contextos propios,
- el binding mínimo de sesión,
- y el endpoint de bootstrap.

## 2. Por qué va en este orden

Debe ir primero porque todas las fases posteriores necesitan una identidad estable y una frontera de dominio clara. Sin surface, router, contexto y sesión no se puede:
- crear `attempt_id`,
- asociar `recording_id`,
- colgar una app pública nueva,
- ni lanzar evaluaciones que sepan en qué flujo y contexto viven.

## 3. Archivos nuevos a crear

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
```

## 4. Archivos actuales a tocar

- `backend/api/app.py`
- `backend/sessions/surface_scope.py`
- `docs/comunicacion/README.md` solo para navegación documental, si hiciera falta ajustar enlaces cruzados

## 5. Cambios exactos por archivo

### `backend/comunicacion/api/router.py`
**Qué irá dentro**
- `APIRouter(prefix="/api/comunicacion", tags=["comunicacion"])`
- endpoint `POST /sessions/bootstrap`
- placeholders documentados para endpoints futuros (`/attempts`, `/submit`, `/evaluations/{id}`) sin implementarlos aún en esta fase
- traducción de errores de contexto/sesión a `HTTPException`

**Responsabilidad exacta**
- aceptar request Pydantic,
- delegar en `session_service.ensure_communication_session(...)`,
- devolver `SessionBootstrapResponse`.

### `backend/comunicacion/models.py`
**Qué irá dentro**
- `CommunicationSessionBootstrapRequest`
- `CommunicationSessionBootstrapResponse`
- `CommunicationPresentationConfigRef`
- `CommunicationCapturePolicy`
- tipos auxiliares de bootstrap

**No entra aún**
- contratos de attempt,
- contratos de evaluation,
- contratos de report final.

### `backend/comunicacion/services/session_service.py`
**Qué irá dentro**
- normalización de `user_id` y `session_id`
- generación de identidad pública si faltan IDs
- resolución de `context_id` / `public_slug`
- `ensure_session_surface(..., surface="comunicacion")`
- binding del contexto de comunicación en `world_state`
- lectura de `presentation_config.json`, `activity_brief.json` y `capture_policy.json`
- aplicación de TTL `bootstrap` o `active`

### `backend/api/app.py`
**Cambio mínimo exacto recomendado**
- importar `comunicacion_router`
- definir `COMUNICACION_DIR = BACKEND_DIR / "comunicacion_app"`
- crear helper `_comunicacion_index_response()`
- crear helper `_comunicacion_asset_response(*relative_parts)`
- `app.include_router(comunicacion_router)`
- montar `app.mount("/comunicacion", StaticFiles(...), name="comunicacion")`
- añadir rutas explícitas similares a `/interfaz_usuario/app.js` y `/interfaz_usuario/{public_slug}`

### `backend/sessions/surface_scope.py`
**Cambio mínimo exacto**
```python
SessionSurface = Literal['optimizador', 'interfaz_usuario', 'comunicacion']
```

Y ampliar el conjunto aceptado en `read_session_surface(...)` a:
```python
{'optimizador', 'interfaz_usuario', 'comunicacion'}
```

Nada más. No registry dinámica, no enum nueva, no refactor general.

## 6. Funciones / clases / modelos

### Funciones nuevas sugeridas

```python
def ensure_communication_session(
    *,
    user_id: str | None,
    session_id: str | None,
    context_id: str | None = None,
    public_slug: str | None = None,
) -> dict[str, Any]:
    ...
```

```python
def resolve_public_communication_selection(
    *,
    context_id: str | None,
    public_slug: str | None,
) -> "ResolvedCommunicationSelection":
    ...
```

```python
def ensure_communication_session_context(
    *,
    state: SessionState,
    requested_context_id: str | None = None,
) -> "BoundCommunicationContext":
    ...
```

```python
def resolve_default_communication_context() -> "ResolvedCommunicationContext":
    ...
```

### Modelos Pydantic sugeridos

```python
class CommunicationSessionBootstrapRequest(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    context_id: str | None = None
    public_slug: str | None = None
```

```python
class CommunicationSessionBootstrapResponse(BaseModel):
    user_id: str
    session_id: str
    session_bootstrap_state: Literal['new', 'rehydrated']
    existing_session: bool
    context_id: str
    public_slug: str
    presentation_config: dict[str, Any]
    activity_brief: dict[str, Any]
    capture_policy: dict[str, Any]
```

## 7. Contratos JSON

### `POST /api/comunicacion/sessions/bootstrap` — request
```json
{
  "user_id": null,
  "session_id": null,
  "context_id": null,
  "public_slug": "comunicacion"
}
```

### `POST /api/comunicacion/sessions/bootstrap` — response
```json
{
  "user_id": "iu_xxx",
  "session_id": "sess_xxx",
  "session_bootstrap_state": "new",
  "existing_session": false,
  "context_id": "baseline_current",
  "public_slug": "comunicacion",
  "presentation_config": {
    "version": "1.0.0",
    "theme": "communication"
  },
  "activity_brief": {
    "title": "Presentación breve grabada"
  },
  "capture_policy": {
    "min_duration_ms": 30000,
    "max_duration_ms": 180000,
    "allow_rerecord": true
  }
}
```

## 8. Snippets de código orientativos

### Router
```python
router = APIRouter(prefix='/api/comunicacion', tags=['comunicacion'])

@router.post('/sessions/bootstrap', response_model=CommunicationSessionBootstrapResponse)
def bootstrap_session(payload: CommunicationSessionBootstrapRequest) -> CommunicationSessionBootstrapResponse:
    out = ensure_communication_session(
        user_id=payload.user_id,
        session_id=payload.session_id,
        context_id=payload.context_id,
        public_slug=payload.public_slug,
    )
    return CommunicationSessionBootstrapResponse(**out)
```

### Servicio
```python
def ensure_communication_session(...):
    normalized_user_id, normalized_session_id = _resolve_or_generate_public_identity(...)
    store = get_session_store()
    existing_state = store.get(user_id=normalized_user_id, session_id=normalized_session_id)
    state = existing_state or get_session_state(user_id=normalized_user_id, session_id=normalized_session_id)
    ensure_session_surface(state=state, surface='comunicacion')
    bound_context = ensure_communication_session_context(
        state=state,
        requested_context_id=_resolve_bootstrap_context_id(...),
    )
    resolved_context = resolve_communication_context(bound_context.context_id)
    ttl_scope = 'bootstrap' if existing_state is None else 'active'
    apply_session_ttl(state, scope=ttl_scope, reason='comunicacion_bootstrap')
    return _build_bootstrap_payload(...)
```

### `backend/api/app.py`
```python
from comunicacion.api import router as comunicacion_router

COMUNICACION_DIR = BACKEND_DIR / 'comunicacion_app'
app.include_router(comunicacion_router)

if COMUNICACION_DIR.exists():
    app.mount('/comunicacion', StaticFiles(directory=str(COMUNICACION_DIR), html=True), name='comunicacion')
```

## 9. Tests recomendados

1. `backend/tests/test_public_comunicacion_serving.py`
   - sirve `GET /comunicacion`
   - sirve `GET /comunicacion/app.js`
   - sirve `GET /comunicacion/{public_slug}` si el slug existe

2. `backend/tests/test_comunicacion_bootstrap_api.py`
   - bootstrap con IDs nulos genera identidad nueva
   - bootstrap con misma identidad rehidrata sesión
   - `public_slug` desconocido devuelve 404
   - conflicto de surface devuelve 409 si la sesión ya está ligada a otra surface

3. `backend/tests/test_comunicacion_context_binding.py`
   - persiste contexto de comunicación en sesión
   - no pisa binding previo válido

## 10. Riesgos de la fase

- contaminación accidental de `negociacion` si se intenta reutilizar `negociacion.contexts.*`
- sobre-generalización de `SessionSurface`
- bootstrap demasiado ambicioso que ya intente crear attempt o evaluation
- mezcla de assets entre `interfaz_usuario_app` y `comunicacion_app`

## 11. Criterios de aceptación

- existe namespace `backend/comunicacion/` documentado y listo para implementar
- `backend/api/app.py` tiene definido el cambio mínimo para servir `/comunicacion`
- el bootstrap queda fijado con request/response concretos
- `comunicacion` tiene contexto propio y binding propio
- la sesión queda ligada a la nueva surface sin tocar la lógica de negociación

## 12. Qué NO entra aún en esta fase

- create attempt
- upload de vídeo
- `recording_id`
- evaluación
- renderer del informe
- integración embed final
