# Fase 6 — Endurecimiento, embed final y compatibilidad lógica con Moodle

## 1. Objetivo de la fase

Cerrar el MVP desde el punto de vista de salida final del flujo: serialización estable del resultado, bridge embed, ACK lógico, payload final autocontenido y checklist final de endurecimiento, todo ello sin inventar la implementación concreta del repo Moodle.

## 2. Por qué va en este orden

Va al final porque necesita que el informe, el vídeo, el renderer y la evaluación ya estén cerrados. Solo entonces tiene sentido empaquetar un `final_result` consistente que pueda enviarse fuera del simulador.

## 3. Archivos nuevos a crear

```text
backend/comunicacion/
  final_result_models.py
backend/tests/
  test_comunicacion_final_result_contract.py
```

## 4. Archivos actuales a tocar

- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/report_view.js`
- `backend/comunicacion/api/router.py` si se expone endpoint auxiliar de salida final o de lectura consolidada
- `backend/tests/test_embed_final_result_contract.py` solo como referencia; mejor crear tests paralelos

## 5. Cambios exactos por archivo

### `backend/comunicacion_app/app.js`
Responsabilidad:
- construir `final_result` desde report + exportables + media refs
- emitir mensaje a `window.parent`
- registrar ACK pendiente
- aceptar `final_result_saved` con correlación segura

### `backend/comunicacion/final_result_models.py`
Responsabilidad:
- definir el shape lógico final a preservar
- documentar qué campos son obligatorios para cuaderno/Moodle

### `backend/comunicacion_app/report_view.js`
Responsabilidad:
- exponer serialización estable (`summary_html`, PNG, JSON)
- ayudar a calcular `payload_hash` si se prefiere en frontend

## 6. Funciones / clases / modelos

### Shape exacto del `final_result` lógico sugerido

```json
{
  "schema_version": "comunicacion_final_result.v1",
  "activity_id": "comunicacion",
  "session_id": "sess_abc",
  "user_id": "iu_abc",
  "attempt_id": "att_01HXYZ",
  "recording_id": "rec_01HXYZ",
  "evaluation_id": "eval_01HXYZ",
  "context_id": "baseline_current",
  "public_slug": "comunicacion",
  "summary_html": "<section>...</section>",
  "report_snapshot_png_data_url": "data:image/png;base64,...",
  "payload_json": {
    "schema_version": "ui_communication_report.v1",
    "evaluation_id": "eval_01HXYZ"
  },
  "media": {
    "video_ref": "storage://tmp/rec_01HXYZ/original.webm",
    "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg",
    "duration_ms": 92314,
    "mime_type": "video/webm"
  },
  "payload_hash": "sha256:...",
  "created_at": "2026-03-23T00:00:00Z"
}
```

### Qué debe contener sí o sí

- identidad de sesión y evaluación,
- `payload_json` del informe,
- `summary_html`,
- snapshot del informe,
- `video_ref` o referencia equivalente,
- `payload_hash`,
- metadatos temporales y de contexto.

### Funciones exactas sugeridas

```javascript
async function buildCommunicationFinalResultPayload(report, options = {}) {}
async function emitCommunicationFinalResultLifecycle(report, options = {}) {}
function buildCommunicationEmbedEnvelope(payload, options = {}) {}
function registerPendingCommunicationFinalAck(payload, envelope) {}
function handleCommunicationEmbeddedSaveAck(event) {}
```

```python
class CommunicationFinalResultV1(BaseModel):
    schema_version: Literal['comunicacion_final_result.v1']
    activity_id: str
    session_id: str
    user_id: str
    attempt_id: str
    recording_id: str
    evaluation_id: str
    context_id: str
    public_slug: str
    summary_html: str
    report_snapshot_png_data_url: str
    payload_json: dict[str, Any]
    media: dict[str, Any]
    payload_hash: str
    created_at: str
```

## 7. Contratos JSON

### Envelope lógico `final_result`
```json
{
  "ns": "gestionce.simulator",
  "v": 1,
  "type": "final_result",
  "correlation_id": "comm-final-001",
  "payload": {
    "schema_version": "comunicacion_final_result.v1",
    "activity_id": "comunicacion",
    "session_id": "sess_abc",
    "evaluation_id": "eval_01HXYZ",
    "summary_html": "<section>...</section>",
    "report_snapshot_png_data_url": "data:image/png;base64,...",
    "payload_json": {"schema_version": "ui_communication_report.v1"},
    "media": {
      "video_ref": "storage://tmp/rec_01HXYZ/original.webm",
      "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg"
    },
    "payload_hash": "sha256:..."
  }
}
```

### ACK esperado, sin inventar Moodle
```json
{
  "ns": "gestionce.simulator",
  "v": 1,
  "type": "final_result_saved",
  "payload": {
    "status": "ok",
    "session_id": "sess_abc",
    "evaluation_id": "eval_01HXYZ",
    "payload_hash": "sha256:...",
    "correlation_id": "comm-final-001"
  }
}
```

## 8. Snippets de código orientativos

### Construcción del payload final
```javascript
async function buildCommunicationFinalResultPayload(report) {
  const summaryHtml = window.CommunicationReportView.serializeCommunicationReportToHtml(report);
  const snapshot = await window.CommunicationReportView.captureCommunicationReportPngDataUrl(report, {
    rootElement: document.getElementById('communicationReportRoot'),
  });
  return {
    schema_version: 'comunicacion_final_result.v1',
    activity_id: 'comunicacion',
    session_id: state.session.session_id,
    user_id: state.session.user_id,
    attempt_id: state.attempt.attempt_id,
    recording_id: report.media.recording_id,
    evaluation_id: report.evaluation_id,
    context_id: state.session.context_id,
    public_slug: state.session.public_slug,
    summary_html: summaryHtml,
    report_snapshot_png_data_url: snapshot,
    payload_json: report,
    media: report.media,
    payload_hash: derivePayloadHash(report, summaryHtml, snapshot),
    created_at: new Date().toISOString(),
  };
}
```

### Emisión embed
```javascript
async function emitCommunicationFinalResultLifecycle(report) {
  const payload = await buildCommunicationFinalResultPayload(report);
  const envelope = buildCommunicationEmbedEnvelope(payload);
  registerPendingCommunicationFinalAck(payload, envelope);
  window.parent.postMessage(envelope, '*');
}
```

## 9. Tests recomendados

1. `backend/tests/test_comunicacion_final_result_contract.py`
   - construye payload final con `summary_html`, PNG, JSON y `video_ref`
   - acepta ACK correcto
   - rechaza ACK con `payload_hash` o `correlation_id` incorrectos

2. `backend/tests/test_comunicacion_report_export_contract.py`
   - confirma que el report puede serializarse antes de emitirse

3. smoke tests manuales en embed
   - emite `final_result`
   - recibe `final_result_saved`
   - muestra estado visual de guardado

## 10. Riesgos de la fase

- intentar definir endpoints o tablas concretas de Moodle sin acceso al repo
- no preservar `video_ref` en el payload final
- no generar `summary_html` ni snapshot desde la app
- romper compatibilidad conceptual con negociación cambiando demasiado el patrón de embed

## 11. Criterios de aceptación

- el simulador sabe producir un `final_result` autocontenido
- el payload conserva HTML, JSON, snapshot y referencia al vídeo
- el contrato sigue el patrón lógico ya usado por negociación
- queda perfectamente delimitado qué parte sigue pendiente hasta inspeccionar Moodle/cuaderno
- existe checklist final del MVP

### Checklist final del MVP
- bootstrap de sesión completado
- create attempt completado
- attach/upload recording completado
- submit de evaluación completado
- report final con vídeo pequeño arriba completado
- export HTML/JSON/PNG completado
- emisión `final_result` lógica completada
- compatibilidad futura con persistencia externa documentada

## 12. Qué NO entra aún en esta fase

- integración real con `mod_simulador` o `Mi cuaderno`
- persistencia real del vídeo en Moodle
- endpoints concretos del LMS
- decisiones de storage definitivo externas a esta repo
