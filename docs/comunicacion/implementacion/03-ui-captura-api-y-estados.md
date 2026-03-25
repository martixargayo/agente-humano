# 03 — UI de captura, API y estados

## 1. Resumen ejecutivo

La UI de `comunicacion` debe construirse como una app nueva y contenida, con una máquina de estados pequeña y explícita. El frontend actual del repo aporta patrones muy útiles —cliente `api()`, embed, polling, export de report— pero no conviene reaprovechar su flujo central de negociación, porque está altamente acoplado a audio-turnos, TTS/STT y feedback conversacional.

La recomendación MVP es una app estática nueva bajo `backend/comunicacion_app/` con cuatro archivos:
- `index.html`
- `app.js`
- `report_view.js`
- `styles.css`

---

## 2. Estructura exacta de la app nueva

```text
backend/comunicacion_app/
  index.html
  app.js
  report_view.js
  styles.css
```

## 2.1 Responsabilidad por archivo

### `backend/comunicacion_app/index.html`
- shell de pantallas de la actividad,
- contenedores para preview de cámara, revisión, progreso y report,
- marca embed/no embed,
- carga `app.js` y `report_view.js`.

### `backend/comunicacion_app/app.js`
- bootstrap de sesión,
- gestión de permisos,
- `MediaRecorder`,
- creación de attempt,
- upload de recording,
- submit y polling,
- bridge embed,
- coordinación de pantallas.

### `backend/comunicacion_app/report_view.js`
- renderer del informe de comunicación,
- export HTML/JSON/PNG,
- integración vídeo + timeline + bloques.

### `backend/comunicacion_app/styles.css`
- estilos puros de la app,
- evita meter CSS inmenso inline como en `interfaz_usuario_app/index.html`,
- facilita iteración visual sin tocar lógica.

---

## 3. Máquina de estados de UI

## 3.1 Estados recomendados

| Estado | Qué se ve | Acciones permitidas | Eventos de salida | Errores típicos |
|---|---|---|---|---|
| `intro` | briefing + botón empezar | continuar | `BOOTSTRAP_OK` | bootstrap fallido |
| `permissions` | permisos cámara/mic + selección de dispositivos | conceder permisos, reintentar | `PERMISSIONS_GRANTED` | `PERMISSION_DENIED` |
| `preview` | preview en vivo y controles de preparación | iniciar grabación, cambiar device | `START_RECORDING` | device unavailable |
| `recording` | vídeo en vivo + cronómetro + botón parar | parar grabación, cancelar | `RECORDING_STOPPED` | recorder error |
| `review` | reproducción local del blob + acciones | repetir, subir y enviar | `RERECORD`, `UPLOAD_REQUESTED` | blob inválido |
| `uploading` | progress indicator | cancelar si MVP lo permite | `UPLOAD_OK` | upload error |
| `processing` | estado del job + fases | esperar, reintentar en error | `EVAL_COMPLETED` | polling error |
| `report` | vídeo final + informe | revisar, exportar, emitir embed | `EMBED_SENT` | render error |
| `error` | mensaje y CTA | reintentar/volver | `RETRY` | n/a |

## 3.2 Secuencia recomendada

```text
intro
  -> permissions
  -> preview
  -> recording
  -> review
  -> uploading
  -> processing
  -> report
```

### Decisión cerrada
No fusionar `preview`, `recording` y `review` en un único estado gordo. La separación hará mucho más fácil mantener el frontend.

---

## 4. Estado JS recomendado

## 4.1 Shape de estado

```json
{
  "session": {
    "user_id": null,
    "session_id": null,
    "context_id": null,
    "public_slug": null,
    "bootstrap_state": "unknown"
  },
  "context": {
    "presentation_config": null,
    "capture_policy": null
  },
  "ui": {
    "screen": "intro",
    "busy": false,
    "error_message": null,
    "embed_mode": false
  },
  "capture": {
    "permission_camera": "prompt",
    "permission_mic": "prompt",
    "selected_video_device_id": null,
    "selected_audio_device_id": null,
    "stream_active": false,
    "is_recording": false,
    "media_recorder_mime_type": null,
    "duration_ms": 0,
    "blob_url": null,
    "blob_size_bytes": 0
  },
  "attempt": {
    "attempt_id": null,
    "status": null,
    "rerecord_count": 0
  },
  "upload": {
    "in_flight": false,
    "progress_ratio": null,
    "recording_id": null,
    "video_ref": null,
    "poster_frame_ref": null
  },
  "evaluation": {
    "evaluation_id": null,
    "status": null,
    "stage_latencies_ms": null
  },
  "report": {
    "data": null,
    "video_ref": null,
    "poster_frame_ref": null
  },
  "embed": {
    "ready_sent": false,
    "pending_final_ack": false,
    "last_ack_signature": null
  }
}
```

## 4.2 Estado que no conviene guardar
- transcript completa en memoria del cliente si no hace falta,
- frames extraídos,
- features derivadas largas,
- blobs históricos de varias rerecords simultáneas.

---

## 5. Funciones frontend propuestas

## 5.1 Bootstrap / contexto

```javascript
async function bootstrapCommunicationSession() {}
async function ensurePresentationShell() {}
function readCommunicationSlugFromUrl() {}
function readEmbedModeFromUrl() {}
```

### Responsabilidad
- resolver sesión/contexto,
- inicializar layout,
- detectar embed.

## 5.2 Permisos y dispositivos

```javascript
async function requestCapturePermissions() {}
async function listCaptureDevices() {}
async function openPreviewStream({ videoDeviceId, audioDeviceId }) {}
function stopPreviewStream() {}
```

### Responsabilidad
- pedir `getUserMedia`,
- enumerar dispositivos,
- abrir preview de cámara.

## 5.3 Recording lifecycle

```javascript
async function createAttempt() {}
async function startRecording() {}
async function stopRecording() {}
async function resetRecordingReview() {}
```

### Responsabilidad
- crear `attempt_id`,
- iniciar/parar `MediaRecorder`,
- generar blob y `blob_url`,
- preparar pantalla de review.

## 5.4 Upload / submit / polling

```javascript
async function uploadRecording() {}
async function submitAttempt() {}
async function pollEvaluation(evaluationId) {}
async function fetchCommunicationReport(evaluationId) {}
```

### Responsabilidad
- registrar recording,
- disparar job,
- seguir estado,
- traer report.

## 5.5 Report / embed

```javascript
function renderReport(report) {}
function emitFinalEmbedResult(report) {}
function installEmbedAckListener() {}
```

---

## 6. Snippets de código orientativos

## 6.1 Bootstrap

```javascript
async function bootstrapCommunicationSession() {
  const payload = {
    public_slug: readCommunicationSlugFromUrl(),
  };
  const out = await api('/api/comunicacion/sessions/bootstrap', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then((r) => r.json());

  state.session.user_id = out.user_id;
  state.session.session_id = out.session_id;
  state.session.context_id = out.context_id;
  state.context.presentation_config = out.presentation_config;
  state.context.capture_policy = out.capture_policy;
}
```

## 6.2 `getUserMedia`

```javascript
async function requestCapturePermissions() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('getUserMedia no soportado');
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    video: true,
    audio: true,
  });
  return stream;
}
```

## 6.3 `MediaRecorder`

```javascript
async function startRecording() {
  const stream = await openPreviewStream({
    videoDeviceId: state.capture.selected_video_device_id,
    audioDeviceId: state.capture.selected_audio_device_id,
  });
  const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
    ? 'video/webm;codecs=vp9,opus'
    : 'video/webm;codecs=vp8,opus';

  const chunks = [];
  const recorder = new MediaRecorder(stream, { mimeType });
  recorder.ondataavailable = (evt) => {
    if (evt.data && evt.data.size > 0) chunks.push(evt.data);
  };
  recorder.onstop = () => {
    const blob = new Blob(chunks, { type: mimeType });
    state.capture.blob_url = URL.createObjectURL(blob);
    state.capture.blob_size_bytes = blob.size;
    state.capture.recorded_blob = blob;
  };
  recorder.start(1000);
  state.capture.is_recording = true;
}
```

## 6.4 Upload del blob

```javascript
async function uploadRecording() {
  const blob = state.capture.recorded_blob;
  if (!blob || !state.attempt.attempt_id) throw new Error('recording_missing');

  const payload = {
    user_id: state.session.user_id,
    session_id: state.session.session_id,
    mime_type: blob.type || 'video/webm',
    duration_ms: state.capture.duration_ms,
    video_ref: 'storage://placeholder/original.webm',
    poster_frame_ref: null,
    capture_meta: {
      width: 1280,
      height: 720,
      fps: 30,
    },
  };

  const out = await api(`/api/comunicacion/attempts/${state.attempt.attempt_id}/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then((r) => r.json());

  state.upload.recording_id = out.recording.recording_id || out.recording_id;
}
```

## 6.5 Polling

```javascript
async function pollEvaluation(evaluationId) {
  const out = await api(`/api/comunicacion/evaluations/${evaluationId}`, {
    method: 'GET',
  }).then((r) => r.json());

  state.evaluation.status = out.status;
  if (out.status === 'completed') {
    await fetchCommunicationReport(evaluationId);
    state.ui.screen = 'report';
    return;
  }
  if (out.status === 'failed') {
    state.ui.error_message = out.error || 'La evaluación no pudo completarse';
    state.ui.screen = 'error';
    return;
  }
  window.setTimeout(() => pollEvaluation(evaluationId), 1700);
}
```

## 6.6 Bridge embed

```javascript
function emitFinalEmbedResult(report) {
  const payload = {
    activity_type: 'comunicacion',
    evaluation_id: state.evaluation.evaluation_id,
    attempt_id: state.attempt.attempt_id,
    recording_id: state.upload.recording_id,
    video_ref: report.media?.video_ref || null,
    payloadjson: report,
  };
  emitEmbedMessage('final_result_available', {
    evaluation_id: state.evaluation.evaluation_id,
    activity_type: 'comunicacion',
  });
  emitEmbedMessage('final_result', payload, { requiresAck: true });
}
```

---

## 7. Integración con el frontend actual

## 7.1 Qué utilidades conviene copiar/adaptar de `interfaz_usuario_app/app.js`
- `api(path, opts)` para parsing uniforme de errores.
- `readEmbedModeFromUrl()`.
- `emitEmbedMessage(...)`.
- `handleEmbeddedSaveAck(...)` / listener de ACK.
- `pollEvaluationStatus(...)` como patrón.
- manejo de `Retry-After` y estado busy.

## 7.2 Qué no conviene reaprovechar
- modos `talk/write`.
- control de finish button.
- flujo de TTS/STT por turnos.
- estado de conversación y reply del agente.
- overlays y estados del avatar.

## 7.3 Qué abstraería en helpers comunes si más adelante merece la pena
Solo si se justifica tras un primer corte funcionando:
- `api_client.js`
- `embed_bridge.js`
- `polling.js`

### Decisión cerrada de esta fase
No abrir aún una refactorización compartida entre apps. Primero conviene duplicar/reutilizar selectivamente para no romper negociación.

## 7.4 Qué no tocaría para no romper negociación
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/feedback_report_view.js`

---

## 8. Recomendación final del bloque

La UI de `comunicacion` debe ser una app pequeña, de estados explícitos, con fuerte separación respecto al frontend de negociación. El mejor equilibrio para MVP es copiar solo la infraestructura madura de embed/polling/api y construir una experiencia de captura centrada en preview → recording → review → upload → processing → report.
