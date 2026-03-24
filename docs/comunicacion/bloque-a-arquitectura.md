# Bloque A — Arquitectura y encaje en la repo

## 1. Resumen ejecutivo del bloque

El repositorio ya contiene un patrón arquitectónico reusable para actividades de primera clase: **routing dedicado**, **surface propia**, **binding de sesión**, **resolución de contexto oficial**, **presentation config**, **pipeline de evaluación desacoplado** y **tests de convivencia entre contextos/superficies**. Sin embargo, ese patrón está hoy materializado casi exclusivamente alrededor de `negociacion` y su superficie pública `interfaz_usuario`.

La recomendación arquitectónica es incorporar `comunicacion` como **nuevo dominio paralelo**, no como contexto dentro de `backend/negociacion`, y no como extensión menor del router de `interfaz_usuario`. Debe tener su propio árbol de módulos, surface, resolución de contextos, contratos de bootstrap/turnless-activity, ingestión de recording y conexión específica con evaluación. La infraestructura transversal actual —`FastAPI`, sesiones, lifecycle TTL, locks, slug resolution, repositorio de jobs y embed final— sí puede y debe ser reaprovechada.

## 2. Estado actual del repo relevante para este bloque

### 2.1 App FastAPI y montaje de superficies
La app principal vive en `backend/api/app.py`. Ahí se monta:
- la surface pública estática `/interfaz_usuario`,
- routers incluidos por `app.include_router(optimizador_router)` y `app.include_router(interfaz_usuario_router)`,
- assets de la UI pública,
- y la health de runtime de sesiones. Esto confirma que el proyecto ya soporta múltiples superficies montadas en una sola app principal. 

### 2.2 Surface pública de negociación
`backend/interfaz_usuario/__init__.py` define un router con prefijo `/api/interfaz_usuario` e incluye además `evaluacion.api.router` bajo la misma superficie. Esa surface expone:
- bootstrap de sesión,
- nueva conversación,
- finalización de sesión,
- turno de negociación,
- feedback evaluation reutilizando el router compartido.

Conclusión: la negociación pública no pasa por los endpoints legacy `/chat` o `/negociar`, sino por una surface segura e independiente. Ese patrón es excelente referencia para `comunicacion`.

### 2.3 Binding de surface y binding de contexto
El repo fija dos tipos de binding en sesión:
- `surface` en `backend/sessions/surface_scope.py`,
- `context` en `backend/negociacion/contexts/session_binding.py`.

Esto evita mezclar dos experiencias distintas sobre la misma sesión y evita también reutilizar una sesión con contexto incompatible. Este patrón es reutilizable para `comunicacion`, pero hoy el `Literal` de `SessionSurface` solo contempla `'optimizador'` e `'interfaz_usuario'`.

### 2.4 Contextos oficiales y slugs públicos
`backend/negociacion/contexts/resolver.py` resuelve contextos oficiales con:
- `flow_id`,
- `context_id`,
- `context_version`,
- `public_slug`,
- `prompts_dir`,
- assets y presentation.

`backend/negociacion/contexts/public_mapping.py` permite resolver entradas públicas por slug y detectar conflictos entre `context_id` y `public_slug`.

Conclusión: el repo ya tiene un patrón maduro de context packs versionados + slugs públicos. `comunicacion` debe copiar este patrón, pero en un namespace de dominio separado.

### 2.5 Evaluación asíncrona actual
La evaluación actual vive en `backend/evaluacion/`. El router `backend/evaluacion/api/router.py` expone la API de jobs. El servicio `backend/evaluacion/engine/service.py` orquesta estados y ejecuta `building_inputs`, `running_core`, `running_trajectory`, `assembling_report`. Esto es reusable como infraestructura, pero no como contrato de dominio, ya que `DomainContext`, `FeedbackInputBundleV1` y `NegotiationDomainRubricV1` están tipados exclusivamente para negociación.

## 3. Qué reutilizar del código actual

### 3.1 Reutilización directa

#### `backend/api/app.py`
Debe seguir siendo el punto de montaje principal. Serviría como base para:
- montar una nueva surface estática (`/comunicacion` o `/interfaz_comunicacion`),
- incluir un nuevo router `comunicacion_router`,
- exponer assets públicos de la nueva app.

#### `backend/sessions/state.py`
Proporciona:
- `SessionState`,
- `SessionEnvelope`,
- `SessionBindingPayload`,
- `SessionContinuityPayload`,
- store memory/redis,
- export/hydration.

Es la base natural para representar la identidad y continuidad de una actividad `comunicacion`, aunque hoy el envelope extrae `negotiation_context` y `negotiation_canonical` explícitamente. Esa asimetría es un riesgo a documentar.

#### `backend/sessions/lifecycle.py`
Reusable tal cual para TTL de bootstrap, actividad activa y finalización.

#### `backend/sessions/session_lock.py`
Reusable tal cual para exclusión mutua al grabar, subir, enviar o finalizar intentos.

#### `backend/evaluacion/api/router.py` + `backend/evaluacion/engine/service.py`
Sirven como referencia de API y job engine asíncrono. La reutilización recomendable es estructural, no contractual: mismo patrón de creación de job, consulta de estado y consulta de report, pero con nuevos contratos y posiblemente nuevos estados intermedios.

#### `backend/interfaz_usuario_app/app.js`
Reutilizable como base conceptual para:
- bootstrap de sesión,
- polling de evaluación,
- manejo de errores de red y `Retry-After`,
- bridge embed con `window.parent.postMessage(...)`,
- ACK correlacionado de `final_result_saved`.

### 3.2 Reutilización por patrón, no por copia literal

#### `backend/negociacion/contexts/*`
No debe importarse para `comunicacion`, pero sí sirve como blueprint de:
- manifest oficial,
- slug público,
- contexto versionado,
- binding de contexto en sesión,
- selección pública y conflictos.

#### `backend/interfaz_usuario/services.py`
Sirve como referencia del ciclo de vida de una activity pública:
- bootstrap,
- binding de surface,
- binding de contexto,
- TTL,
- locks,
- sesión rehidratada,
- finalización.

Para `comunicacion` convendría un servicio paralelo con semántica propia: `ensure_communication_session`, `start_recording_attempt`, `finalize_recording_attempt`, `submit_recording_for_evaluation`, etc.

## 4. Qué habría que crear nuevo

## 4.1 Nuevo namespace de dominio
Propuesta mínima de organización:

```text
backend/comunicacion/
  __init__.py
  router.py
  models.py
  services.py
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
      evaluation/
        report_manifest.json
  storage/
    __init__.py
    models.py
    repository.py
```

### Responsabilidad por módulo
- `router.py`: endpoints HTTP propios del flujo.
- `models.py`: contratos API de bootstrap, upload, submit, review, result.
- `services.py`: coordinación de sesiones, attempts, submit y polling metadata.
- `contexts/*`: patrón equivalente a negociación, pero con `flow_id = comunicacion`.
- `storage/*`: referencias persistentes a grabaciones y artefactos derivados.

## 4.2 Nuevo namespace de evaluación de comunicación

```text
backend/evaluacion/domains/communication/
  __init__.py
  extractor.py
  context_resolver.py
  assets_loader.py
  rubric_loader.py

backend/evaluacion/contracts/
  communication_models.py

backend/evaluacion/engine/
  communication_assembler.py
  communication_flow_config.py
```

### Justificación
`evaluacion/contracts/models.py` está fuertemente centrado en negociación:
- `domain: Literal["negociacion"]`
- bloques `valores/vision/relacion/proceso`
- trayectoria por `turns`
- outcome de acuerdo negociador.

Intentar reutilizarlo degradaría el diseño desde el día 1.

## 4.3 Nueva surface pública
Dos opciones limpias:

### Opción recomendada
- app estática nueva: `backend/comunicacion_app/`
- mounted en `/comunicacion`
- API en `/api/comunicacion`

### Opción alternativa
- reusar `interfaz_usuario_app` como shell multi-actividad.

Diagnóstico: la opción alternativa tiene más riesgo porque `app.js` actual está cargado de estado específico de negociación y feedback conversacional. Técnica y organizativamente es preferible una app pública nueva.

## 5. Propuesta de organización

## 5.1 Estructura de rutas backend sugerida

```text
POST /api/comunicacion/sessions/bootstrap
POST /api/comunicacion/attempts
POST /api/comunicacion/attempts/{attempt_id}/upload
POST /api/comunicacion/attempts/{attempt_id}/submit
GET  /api/comunicacion/attempts/{attempt_id}
POST /api/comunicacion/evaluations
GET  /api/comunicacion/evaluations/{evaluation_id}
GET  /api/comunicacion/evaluations/{evaluation_id}/report
GET  /api/comunicacion/assets/{context_id}/{asset_path}
```

### Motivación
A diferencia de negociación, `comunicacion` no es un flujo por turnos. Necesita distinguir claramente:
- identidad de sesión,
- intento de grabación,
- media subida,
- submit de evaluación,
- y resultado.

## 5.2 Surface y slug público
Si se replica el patrón de negociación, debería haber:
- `public_slug = comunicacion` para baseline,
- potenciales variantes futuras: `comunicacion-presentacion`, `comunicacion-ventas`, etc.

Pero estos slugs deben resolverse desde `backend/comunicacion/contexts/public_mapping.py`, no desde `backend/negociacion/contexts/public_mapping.py`.

## 5.3 Binding de sesión
Recomendación:
- nueva `surface`: `comunicacion_publica` o `comunicacion`.
- nuevo bloque de contexto: `communication_context`.
- nuevo bloque de estado de runtime: `communication_runtime`.

### Riesgo explícito
`SessionSurface` actual es un `Literal['optimizador', 'interfaz_usuario']`. Eso obliga a decidir entre:
1. ampliar ese `Literal`,
2. generalizarlo a string validada,
3. o introducir una capa paralela.

Diagnóstico: lo más limpio a medio plazo es convertir `SessionSurface` en un conjunto extensible validado, porque `comunicacion` no será la última activity específica.

## 6. Contratos de datos o schemas sugeridos

## 6.1 Bootstrap
```json
{
  "user_id": "optional",
  "session_id": "optional",
  "context_id": "optional",
  "public_slug": "optional"
}
```

Respuesta sugerida:
```json
{
  "user_id": "u_...",
  "session_id": "sess_...",
  "session_bootstrap_state": "new",
  "existing_session": false,
  "context_id": "baseline_current",
  "public_slug": "comunicacion",
  "presentation_config": {},
  "capture_constraints": {
    "video": true,
    "audio": true,
    "max_duration_seconds": 180
  }
}
```

## 6.2 Attempt identity
```json
{
  "attempt_id": "att_xxx",
  "status": "draft",
  "session_id": "sess_xxx",
  "context_id": "baseline_current",
  "capture_policy": {
    "min_seconds": 30,
    "max_seconds": 180,
    "allow_rerecord": true
  }
}
```

## 7. Rutas, funciones, clases o módulos concretos que sirven de base

### Referencias backend
- `backend/interfaz_usuario/services.py::ensure_session`
- `backend/interfaz_usuario/services.py::finalize_session`
- `backend/interfaz_usuario/__init__.py::bootstrap_session`
- `backend/negociacion/contexts/resolver.py::resolve_negotiation_context`
- `backend/negociacion/contexts/public_mapping.py::resolve_public_context_selection`
- `backend/negociacion/contexts/session_binding.py::ensure_session_context`
- `backend/sessions/surface_scope.py::ensure_session_surface`
- `backend/sessions/session_lock.py::acquire_session_execution_lock`
- `backend/evaluacion/engine/service.py::create_evaluation`
- `backend/evaluacion/engine/service.py::get_evaluation_status`

### Nuevas firmas sugeridas
No son implementación; son esqueletos de responsabilidad.

```python
# backend/comunicacion/services.py

def ensure_communication_session(*, user_id: str | None, session_id: str | None, context_id: str | None = None, public_slug: str | None = None) -> dict[str, Any]:
    ...


def create_recording_attempt(*, user_id: str, session_id: str) -> dict[str, Any]:
    ...


def register_uploaded_recording(*, user_id: str, session_id: str, attempt_id: str, recording_ref: str, duration_ms: int) -> dict[str, Any]:
    ...


def submit_attempt_for_evaluation(*, user_id: str, session_id: str, attempt_id: str) -> dict[str, Any]:
    ...
```

## 8. Riesgos y decisiones pendientes

### Riesgo: contaminación del namespace `interfaz_usuario`
Si `comunicacion` se mete dentro de `/api/interfaz_usuario`, la separación semántica se debilita. El router actual ya mezcla bootstrap/turn/finalize + feedback de negociación. Mejor evitarlo.

### Riesgo: SessionEnvelope sesgado a negociación
`export_session_envelope(...)` y `hydrate_session_state(...)` contienen referencias explícitas a `negotiation_context` y `negotiation_canonical`. Para una arquitectura realmente multi-activity habrá que revisar esta asunción. No es bloqueante hoy, pero sí una deuda visible.

### Decisión pendiente: router de evaluación compartido o separado
Hay dos opciones limpias:
- reutilizar la infraestructura de `evaluacion.api.router` con subrouters por dominio,
- o crear `evaluacion/api/communication_router.py` y montarlo desde `backend/comunicacion/router.py`.

Recomendación: mantener el engine común, pero exponer router específico para `comunicacion` dentro de su surface.

## 9. Recomendación final del bloque

El encaje correcto en la repo es: **nuevo dominio + nueva surface + nuevos contextos + nuevos contratos**, apoyados en la infraestructura común existente. La intervención sobre el flujo `negociacion` debe limitarse a cambios transversales realmente imprescindibles (por ejemplo, generalizar `SessionSurface` o desacoplar ciertas partes del envelope de sesión). Cualquier intento de introducir `comunicacion` como extensión menor de `negociacion` aumentaría el acoplamiento y dificultaría la evolución futura del producto.
