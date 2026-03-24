# Fase 3 — App pública de captura

## 1. Objetivo de la fase

Diseñar la app estática pública de `comunicacion` con un flujo completo de usuario para:
- pedir permisos,
- mostrar preview,
- grabar,
- revisar,
- subir,
- enviar a evaluar,
- y hacer polling básico hasta que exista report.

## 2. Por qué va en este orden

Va después de Fase 2 porque necesita endpoints y contratos estables de bootstrap, attempt y upload. Va antes de cerrar evaluación/report porque el frontend debe quedar preparado para consumir un `evaluation_id` y un report, aunque internamente el motor todavía esté en su versión mínima.

## 3. Archivos nuevos a crear

```text
backend/comunicacion_app/
  index.html
  app.js
  report_view.js
  styles.css
```

## 4. Archivos actuales a tocar

- `backend/api/app.py` para exponer assets y `index.html` de `comunicacion_app`
- `backend/tests/test_public_interfaz_usuario_serving.py` no debería tocarse; se crearán tests paralelos

## 5. Cambios exactos por archivo

### `backend/comunicacion_app/index.html`
Responsabilidades:
- shell general de pantallas
- contenedores para `intro`, `permissions`, `preview`, `recording`, `review`, `processing`, `report`
- `<video>` de preview y `<video>` de review/report
- layout superior del report con espacio reservado para reproductor pequeño
- botones de CTA y contenedores de error/estado

### `backend/comunicacion_app/app.js`
Responsabilidades:
- bootstrap
- permisos y dispositivos
- `MediaRecorder`
- create attempt
- upload recording
- submit attempt
- polling de evaluación
- coordinación de pantallas
- bridge embed mínimo

### `backend/comunicacion_app/report_view.js`
Responsabilidades:
- pintar el informe de `comunicacion`
- montar el vídeo pequeño en la zona superior
- exponer helpers de serialización y captura visual, equivalentes lógicos a los del renderer actual

### `backend/comunicacion_app/styles.css`
Responsabilidades:
- layout de la shell de captura
- estilos del informe
- grid superior `video + resumen`
- responsive para embed e iframe estrecho

## 6. Funciones / clases / modelos

### Máquina de estados completa

```text
intro
 -> permissions
 -> preview
 -> recording
 -> review
 -> uploading
 -> processing
 -> report
 -> error
```

### Shape de estado JS

```json
{
  "session": {"user_id": null, "session_id": null, "context_id": null, "public_slug": null},
  "ui": {"screen": "intro", "busy": false, "error_message": null, "embed_mode": false},
  "capture": {
    "permission_camera": "prompt",
    "permission_mic": "prompt",
    "selected_video_device_id": null,
    "selected_audio_device_id": null,
    "stream_active": false,
    "is_recording": false,
    "blob": null,
    "blob_url": null,
    "duration_ms": 0,
    "mime_type": null
  },
  "attempt": {"attempt_id": null, "status": null, "rerecord_count": 0},
  "upload": {"recording_id": null, "video_ref": null, "poster_frame_ref": null, "progress_ratio": null},
  "evaluation": {"evaluation_id": null, "status": null},
  "report": {"data": null, "video_ref": null, "poster_frame_ref": null}
}
```

### Funciones JS exactas

```javascript
async function bootstrapCommunicationSession() {}
async function requestCapturePermissions() {}
async function listCaptureDevices() {}
async function openPreviewStream({ videoDeviceId, audioDeviceId }) {}
function stopPreviewStream() {}
async function createAttempt() {}
async function startRecording() {}
async function stopRecording() {}
function prepareReviewScreen() {}
async function uploadRecording() {}
async function submitAttempt() {}
async function pollEvaluation(evaluationId) {}
async function fetchCommunicationReport(evaluationId) {}
function renderCommunicationReport(report) {}
function installEmbedAckListener() {}
```

## 7. Contratos JSON

### `POST /api/comunicacion/attempts/{attempt_id}/submit`
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
  "evaluation_id": "eval_01HXYZ",
  "status": "queued"
}
```

### `GET /api/comunicacion/evaluations/{evaluation_id}`
```json
{
  "evaluation_id": "eval_01HXYZ",
  "status": "running",
  "stage": "transcript",
  "report_available": false
}
```

## 8. Snippets de código orientativos

### `getUserMedia`
```javascript
async function requestCapturePermissions() {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: true,
    audio: true,
  });
  state.capture.permission_camera = 'granted';
  state.capture.permission_mic = 'granted';
  return stream;
}
```

### `MediaRecorder`
```javascript
async function startRecording() {
  const stream = await openPreviewStream({
    videoDeviceId: state.capture.selected_video_device_id,
    audioDeviceId: state.capture.selected_audio_device_id,
  });
  const chunks = [];
  const recorder = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp9,opus' });
  recorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) chunks.push(event.data);
  };
  recorder.onstop = () => {
    state.capture.blob = new Blob(chunks, { type: recorder.mimeType });
    state.capture.blob_url = URL.createObjectURL(state.capture.blob);
  };
  recorder.start();
}
```

### Upload
```javascript
async function uploadRecording() {
  const payload = {
    user_id: state.session.user_id,
    session_id: state.session.session_id,
    mime_type: state.capture.mime_type,
    duration_ms: state.capture.duration_ms,
    video_ref: 'storage://tmp/pending/original.webm',
    poster_frame_ref: null,
  };
  return api(`/api/comunicacion/attempts/${state.attempt.attempt_id}/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then((r) => r.json());
}
```

### Polling
```javascript
async function pollEvaluation(evaluationId) {
  while (true) {
    const status = await api(`/api/comunicacion/evaluations/${evaluationId}`).then((r) => r.json());
    if (status.report_available) return status;
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}
```

## 9. Tests recomendados

1. `backend/tests/test_public_comunicacion_serving.py`
   - sirve `index.html`, `app.js`, `report_view.js`, `styles.css`

2. `backend/tests/test_comunicacion_embed_contract_smoke.py`
   - valida que la app puede entrar en modo embed sin romperse

3. tests manuales guiados de navegador
   - permisos concedidos/denegados
   - cambio de dispositivo
   - rerecord
   - paso `review -> uploading -> processing`

4. test de contrato del frontend
   - `app.js` contiene funciones públicas previstas
   - `report_view.js` expone renderer y serializadores esperados

## 10. Riesgos de la fase

- intentar reciclar demasiado código de `interfaz_usuario_app/app.js`
- acoplar la UI a un storage binario aún no decidido
- no separar bien preview, recording y review
- no reservar desde ya el espacio superior del vídeo dentro del informe

## 11. Criterios de aceptación

- existe estructura exacta de `backend/comunicacion_app/`
- la máquina de estados queda completa y acotada
- el frontend usa la API de `comunicacion`, no la de negociación
- queda explícito qué utilidades conviene reutilizar del frontend actual: cliente `api()`, patrón embed, serialización de report, polling básico
- queda explícito qué NO tocar del frontend de negociación: lógica de turnos, TTS/STT, renderer de negociación, overlays específicos

## 12. Qué NO entra aún en esta fase

- transcript real
- scoring real
- assembler final definitivo
- snapshot PNG final
- integración real con Moodle
