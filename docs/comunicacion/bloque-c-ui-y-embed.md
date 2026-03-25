# Bloque C — UI de captura + embed + experiencia de usuario

## 1. Resumen ejecutivo del bloque

El frontend actual del repo demuestra que el proyecto ya sabe resolver una activity pública completa con:
- bootstrap de sesión,
- uso de micrófono,
- polling de jobs,
- render de feedback,
- y bridge embed robusto hacia Moodle con ACK correlacionado.

Pero esa app (`backend/interfaz_usuario_app/app.js`) está fuertemente acoplada al flujo de negociación: turnos, TTS/STT, finish button, texto escrito, replay de respuesta y feedback post-conversación. Por tanto, para `comunicacion` la recomendación técnica es **crear una app pública nueva o un shell frontend separado**, en vez de sobrecargar la app actual con estados de cámara, preview de vídeo, revisión de toma y subida de media.

El principal reaprovechamiento debe ser de **patrones**: bootstrap, manejo de identidad, polling de evaluación, embed final y cierta parte del sistema de report. No conviene reaprovechar la lógica de interacción principal de `app.js` como base directa del flujo de captura audiovisual.

## 2. Estado actual del repo relevante para este bloque

### 2.1 App pública actual
La surface `/interfaz_usuario` sirve `index.html`, `app.js`, `feedback_report_view.js` y assets contextuales desde `backend/api/app.py`. Los tests validan que:
- la página pública se sirve por slug,
- los assets no dependen de rutas relativas anidadas,
- el informe final se integra con el contrato embed.

### 2.2 Estado frontend actual
`backend/interfaz_usuario_app/app.js` gestiona una cantidad elevada de estado mutable, incluyendo:
- bootstrap de identidad,
- modo embed,
- audio devices,
- grabación de audio vía `MediaRecorder`,
- polling de evaluación,
- estados de error/busy,
- export y serialización del report.

Esto demuestra madurez en navegador y coordinación asíncrona, pero también indica acoplamiento fuerte con la UX actual.

### 2.3 Contrato embed existente
Los tests `backend/tests/test_public_interfaz_usuario_serving.py` y `backend/tests/test_embed_final_result_contract.py` muestran que el frontend actual:
- emite `final_result_available`,
- emite `final_result`,
- usa `window.parent.postMessage(envelope, PARENT_EMBED_ORIGIN)`,
- espera ACK `final_result_saved`,
- valida correlación fuerte.

Este mecanismo es uno de los activos más valiosos para `comunicacion`, porque ya resuelve el paso crítico de entregar resultados al contenedor Moodle/cuaderno.

## 3. Qué reutilizar del código actual

### 3.1 `app.js` como referencia de infraestructura frontend
Reutilizar por concepto:
- `api(path, opts)` con parsing consistente de errores,
- bootstrap de identidad,
- `readEmbedModeFromUrl()`,
- `emitEmbedMessage(...)` y listeners de ACK,
- `pollEvaluationStatus(...)`,
- `showFeedbackView(...)` como idea de shell multinodo.

### 3.2 `feedback_report_view.js`
Sirve como base de:
- dashboard responsive,
- rendering de bloques,
- gráficos SVG,
- serialización a HTML/PNG,
- uso en runtime y en export.

### 3.3 `index.html` actual como referencia de shell full-screen/embed-aware
El HTML actual ya diferencia modo embed/no embed, usa layout inmersivo y admite assetización por contexto. Eso es buen punto de partida para la nueva app, aunque la estructura visual de captura será distinta.

## 4. Qué habría que crear nuevo

## 4.1 Nueva app pública sugerida

```text
backend/comunicacion_app/
  index.html
  app.js
  report_view.js
  styles.css (opcional si se quiere sacar estilos inline)
  assets/
```

### Responsabilidades
- `index.html`: shell de pantallas de captura/revisión/procesado/report.
- `app.js`: lógica de bootstrap, cámara/micrófono, recording lifecycle, upload, polling y embed.
- `report_view.js`: variante del report visual adaptada a comunicación.

## 4.2 Nueva API frontend/backend
La app debería hablar con un router propio (`/api/comunicacion`) y no con `/api/interfaz_usuario`. Esto reduce confusión y evita mezclar contratos de negociación con contratos de comunicación.

## 5. Propuesta de organización de la experiencia

## 5.1 Flujo de pantallas sugerido

### Pantalla 1 — Bootstrap / intro de actividad
Objetivos:
- resolver sesión + contexto,
- mostrar briefing,
- mostrar tiempo máximo,
- mostrar criterios generales,
- indicar permisos requeridos.

### Pantalla 2 — Preparación técnica
Objetivos:
- pedir permisos de cámara y micro,
- detectar dispositivos,
- seleccionar input,
- mostrar preview en vivo,
- validar nivel mínimo de audio/video.

### Pantalla 3 — Grabación
Objetivos:
- empezar/parar grabación,
- mostrar cronómetro,
- mostrar estado de cámara/mic,
- capturar chunks,
- reflejar límites de duración.

### Pantalla 4 — Revisión
Objetivos:
- reproducir vídeo grabado,
- mostrar metadatos básicos,
- permitir repetir,
- permitir enviar.

### Pantalla 5 — Procesado/evaluación
Objetivos:
- subida del archivo,
- polling de job,
- feedback de fases técnicas (`transcribing`, `extracting_audio`, etc.),
- manejo de timeout o error.

### Pantalla 6 — Resultado
Objetivos:
- reproducir vídeo final,
- mostrar informe,
- permitir reabrir/revisualizar,
- emitir contrato embed final.

## 5.2 Estados de cliente necesarios

Propuesta de estado principal:

```json
{
  "session": {
    "user_id": "u_x",
    "session_id": "sess_x",
    "context_id": "baseline_current",
    "public_slug": "comunicacion"
  },
  "ui": {
    "screen": "intro|permissions|recording|review|processing|report|error",
    "embed_mode": true,
    "busy": false
  },
  "capture": {
    "permission_camera": "granted|prompt|denied",
    "permission_mic": "granted|prompt|denied",
    "selected_video_device_id": "cam_x",
    "selected_audio_device_id": "mic_x",
    "is_recording": false,
    "duration_ms": 0,
    "blob_url": null,
    "mime_type": "video/webm"
  },
  "attempt": {
    "attempt_id": "att_x",
    "recording_id": null,
    "status": "draft|uploaded|submitted"
  },
  "evaluation": {
    "evaluation_id": null,
    "status": null,
    "report": null
  }
}
```

## 5.3 Integración cámara y micrófono

### Qué reaprovechar
La app actual ya trabaja con `navigator.mediaDevices`, permisos, errores y fallback de audio. Ese know-how es útil.

### Qué cambiar
Para `comunicacion`, el artefacto principal no es audio puro sino `MediaStream` de vídeo + audio y un `MediaRecorder` orientado a vídeo.

### Riesgos de navegador
- Safari/iOS puede tener restricciones específicas de codec/container.
- `MediaRecorder` no es uniforme entre navegadores para `video/webm`.
- La previsualización y reproducción inmediata del blob puede tensionar memoria si se permiten grabaciones largas.
- En modo embed, permisos de cámara/mic pueden verse afectados por políticas del iframe/contenedor.

## 5.4 Subida de vídeo
La app actual no tiene un flujo de upload binario grande. Por eso para `comunicacion` hace falta decidir explícitamente:
- upload monolítico,
- upload por chunks,
- presigned URL,
- o bridge directo a storage.

Diagnóstico: aunque todavía no se implementa, la UI debe prepararse para que el upload pueda evolucionar sin rehacerse. Eso sugiere encapsular la subida en una función única del frontend.

Firma sugerida:
```javascript
async function uploadRecording({ attemptId, blob, mimeType }) {
  // devuelve recording_id y refs persistidas
}
```

## 6. Contratos de datos o schemas sugeridos

## 6.1 Respuesta de bootstrap para UI de comunicación
```json
{
  "user_id": "u_x",
  "session_id": "sess_x",
  "context_id": "baseline_current",
  "public_slug": "comunicacion",
  "presentation_config": {},
  "capture_policy": {
    "video_required": true,
    "audio_required": true,
    "max_duration_seconds": 180,
    "allow_rerecord": true,
    "accepted_mime_types": ["video/webm", "video/mp4"]
  }
}
```

## 6.2 Respuesta de upload
```json
{
  "attempt_id": "att_x",
  "recording_id": "rec_x",
  "status": "uploaded",
  "recording": {
    "duration_ms": 92314,
    "poster_frame_ref": "storage://.../poster.jpg"
  }
}
```

## 6.3 Respuesta de submit
```json
{
  "attempt_id": "att_x",
  "evaluation_id": "eval_x",
  "status": "queued"
}
```

## 7. Integración Moodle / embed

## 7.1 Qué se puede reaprovechar
El sistema embed actual ya resuelve:
- detección de runtime embebido,
- emisión al parent con origin restringido,
- mensaje de disponibilidad de resultado,
- mensaje final con payload,
- ACK correlacionado.

Esto es una base excelente para `comunicacion`.

## 7.2 Qué debe ampliarse
El payload final de `comunicacion` necesitará adjuntar, además del report:
- referencia reproducible del vídeo,
- poster/thumbnail,
- metadatos de duración,
- identifiers de attempt/recording.

Payload sugerido:
```json
{
  "type": "final_result",
  "payload": {
    "activity_type": "comunicacion",
    "evaluation_id": "eval_x",
    "attempt_id": "att_x",
    "recording_id": "rec_x",
    "video_ref": "storage://.../original.webm",
    "video_poster_ref": "storage://.../poster.jpg",
    "payloadjson": {
      "schema_version": "ui_communication_report.v1"
    }
  }
}
```

### Riesgo explícito
No está decidido si `video_ref` puede salir directamente al contenedor o si debe resolverse a URL firmada temporal desde backend. Esto afecta seguridad, persistencia y revisualización.

## 8. Piezas existentes reutilizables del frontend actual

### Reutilización alta
- cliente `api(...)`
- manejo de `Retry-After`
- polling de estado
- emisión embed/ACK
- serialización y export de report

### Reutilización media
- patrón de shell por pantallas
- tratamiento de errores y busy state
- bootstrap de sesión

### Reutilización baja
- controls de audio device: útiles pero habrá que extenderlos a cámara
- layout principal de avatar
- modos `talk/write`
- finish button y lógica de negociación

## 9. Riesgos técnicos y decisiones pendientes

### Riesgo alto: permisos en iframe/embed
El flujo de cámara y micro puede fallar si el iframe no tiene atributos `allow="camera; microphone"` o si el contenedor padre no los configura correctamente.

### Riesgo alto: codec/container
Dependiendo del navegador, `video/webm` puede no estar disponible o no ser compatible con el pipeline de análisis elegido.

### Riesgo medio: UX de rerecord
Hay que decidir si el intento permite múltiples grabaciones antes de submit o si cada rerecord genera nuevo `recording_id` dentro del mismo `attempt_id`.

### Riesgo medio: peso de media
Grabaciones largas pueden hacer costosa la previsualización local y el upload. La UI debe diseñarse para soportar progress bars, cancelación y reintento.

### Decisión pendiente: app nueva o shell compartida
El diagnóstico sigue recomendando app nueva, pero si producto exige un look&feel unificado podría hacerse una shell común con entrypoints separados. Aun así, la lógica JS de captura debe permanecer segregada.

## 10. Recomendación final del bloque

La UI de `comunicacion` debe implementarse como una **experience app separada**, embebible y conectada a una API específica. Debe reutilizar el know-how del frontend actual en bootstrap, polling y embed, pero no su flujo central de negociación. Esta separación es la mejor garantía para no introducir regresiones en la app pública existente y para poder evolucionar `comunicacion` hacia una experiencia audiovisual compleja sin comprometer la mantenibilidad del repo.
