# 02 — Pipeline recording y artefactos

## 1. Resumen ejecutivo

El objetivo de este bloque es fijar una organización de datos interna **mínima pero robusta** para que `comunicacion` pueda evolucionar sin rehacer el pipeline en cada iteración. La propuesta es separar claramente cuatro niveles:

1. **Attempt**: unidad de interacción del usuario.
2. **Recording**: referencia a la grabación efectiva enviada.
3. **Derived artifacts**: transcript, audio features, visual summary, etc.
4. **Evaluation bundle**: vista consolidada y estable para evaluadores y assembler.

La decisión más importante es qué guardar dónde:
- en `SessionState`: solo referencias activas y estado mínimo,
- en repositorio de comunicación: entidad de negocio (`AttemptRecord`, `RecordingRecord`, `DerivedArtifactRecord`),
- en `artifacts` del job: hashes/refs ligeras y telemetría.

---

## 2. Modelo exacto de entidades

## 2.1 `AttemptRecord`

### Responsabilidad
Representa un intento de la actividad por parte del usuario.

### Campos sugeridos
```json
{
  "attempt_id": "att_01HXYZ",
  "user_id": "iu_abc",
  "session_id": "sess_abc",
  "flow_id": "comunicacion",
  "context_id": "baseline_current",
  "status": "draft",
  "recording_id": null,
  "latest_evaluation_id": null,
  "rerecord_count": 0,
  "created_at": "2026-03-23T00:00:00Z",
  "updated_at": "2026-03-23T00:00:00Z",
  "submitted_at": null,
  "notes": null
}
```

### Obligatorio
- `attempt_id`
- `user_id`
- `session_id`
- `flow_id`
- `context_id`
- `status`
- timestamps

### Opcional
- `recording_id`
- `latest_evaluation_id`
- `submitted_at`
- `notes`

### Estados sugeridos
- `draft`
- `uploaded`
- `submitted`
- `completed`
- `failed`

---

## 2.2 `RecordingRecord`

### Responsabilidad
Describe la grabación principal asociada a un intento.

### Campos sugeridos
```json
{
  "recording_id": "rec_01HXYZ",
  "attempt_id": "att_01HXYZ",
  "user_id": "iu_abc",
  "session_id": "sess_abc",
  "mime_type": "video/webm",
  "duration_ms": 92314,
  "capture_meta": {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "audio_codec": "opus",
    "video_codec": "vp9"
  },
  "storage": {
    "video_ref": "storage://tmp/rec_01HXYZ/original.webm",
    "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg"
  },
  "created_at": "2026-03-23T00:00:00Z"
}
```

### Obligatorio
- `recording_id`
- `attempt_id`
- `mime_type`
- `duration_ms`
- `storage.video_ref`

### Opcional
- `poster_frame_ref`
- detalle de `capture_meta`

---

## 2.3 `DerivedArtifactRecord`

### Responsabilidad
Describe cualquier salida derivada del recording.

### Campos sugeridos
```json
{
  "artifact_id": "art_01HXYZ",
  "recording_id": "rec_01HXYZ",
  "kind": "transcript",
  "version": "v1",
  "storage_ref": "storage://tmp/rec_01HXYZ/transcript.json",
  "content_hash": "sha256:...",
  "created_at": "2026-03-23T00:00:00Z"
}
```

### `kind` sugeridos
- `poster_frame`
- `transcript`
- `audio_features`
- `gesture_analysis`
- `frame_set`
- `bundle_snapshot`

---

## 2.4 `CommunicationEvaluationInput`

### Responsabilidad
Vista consolidada lista para evaluación, no necesariamente persistida como entidad primaria de negocio.

```json
{
  "schema_version": "communication_feedback_input_bundle.v1",
  "evaluation_id": "eval_01HXYZ",
  "session_ref": {"user_id": "iu_abc", "session_id": "sess_abc"},
  "attempt_ref": {"attempt_id": "att_01HXYZ", "recording_id": "rec_01HXYZ"},
  "domain_context": {
    "domain": "comunicacion",
    "flow_id": "comunicacion",
    "context_id": "baseline_current",
    "context_version": "1.0.0"
  },
  "recording": {
    "duration_ms": 92314,
    "video_ref": "storage://tmp/rec_01HXYZ/original.webm",
    "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg"
  },
  "transcript": {},
  "audio_features": {},
  "visual_features": {}
}
```

---

## 3. Estado mínimo viable: qué se guarda dónde

| Ubicación | Qué sí guardar | Qué no guardar |
|---|---|---|
| `SessionState.world_state` | `active_attempt_id`, `last_recording_id`, `latest_evaluation_id`, `capture_status` | blobs binarios, transcript completa, arrays grandes de frames |
| `comunicacion.storage.repository` | `AttemptRecord`, `RecordingRecord`, `DerivedArtifactRecord` | resultados renderizados finales si ya viven en report repository |
| `evaluacion.storage.models.FeedbackJobRecord.artifacts` | hashes, refs, IDs, versiones de pipeline | payloads completos de transcript/features |
| storage binario/JSON externo | vídeo, poster, transcript JSON, features JSON, frame refs | N/A |

### Decisión cerrada
No almacenar vídeo ni transcript completa en `SessionState`.

### Propuesta recomendada de bloque de sesión
```json
{
  "communication_runtime": {
    "active_attempt_id": "att_01HXYZ",
    "last_recording_id": "rec_01HXYZ",
    "latest_evaluation_id": "eval_01HXYZ",
    "capture_status": "uploaded",
    "report_status": "queued"
  }
}
```

---

## 4. Pipeline de derivados

## 4.1 Paso 0 — vídeo bruto

**Input**
- blob/client upload ya persistido como `video_ref`

**Output**
- `RecordingRecord`

**Módulo responsable**
- `backend/comunicacion/services/recording_service.py`

**Función sugerida**
```python
def attach_recording_to_attempt(...) -> RecordingRecord
```

---

## 4.2 Paso 1 — poster frame

**Input**
- `RecordingRecord.storage.video_ref`

**Output**
- `DerivedArtifactRecord(kind="poster_frame")`

**Módulo responsable**
- `backend/comunicacion/processing/video.py`

**Función sugerida**
```python
def extract_poster_frame(*, recording: RecordingRecord) -> DerivedArtifactRecord:
    ...
```

**Formato de salida sugerido**
```json
{
  "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg",
  "timestamp_ms": 500
}
```

---

## 4.3 Paso 2 — frames

### Decisión MVP
No es imprescindible en MVP si la evaluación visual avanzada queda fuera. Puede sustituirse por `poster_frame + visual_summary` vacío o mockeado.

**Input**
- `video_ref`

**Output**
- `DerivedArtifactRecord(kind="frame_set")`

**Función sugerida**
```python
def extract_frame_set(*, recording: RecordingRecord, strategy: str = "uniform_8") -> DerivedArtifactRecord:
    ...
```

**Formato de salida**
```json
{
  "strategy": "uniform_8",
  "frames": [
    {"frame_index": 1, "timestamp_ms": 1000, "image_ref": "storage://.../f001.jpg"}
  ]
}
```

---

## 4.4 Paso 3 — audio extraído

**Input**
- `video_ref`

**Output**
- `audio_ref`

**Módulo responsable**
- `backend/comunicacion/processing/audio.py`

**Función sugerida**
```python
def extract_audio_track(*, recording: RecordingRecord) -> DerivedArtifactRecord:
    ...
```

**Formato de salida**
```json
{
  "audio_ref": "storage://tmp/rec_01HXYZ/audio.wav",
  "sample_rate_hz": 16000,
  "duration_ms": 92314
}
```

---

## 4.5 Paso 4 — transcript

**Input**
- `audio_ref` o `video_ref`

**Output**
- `DerivedArtifactRecord(kind="transcript")`

**Módulo responsable**
- `backend/comunicacion/processing/transcript.py`

**Función sugerida**
```python
def transcribe_recording(*, recording: RecordingRecord, language_hint: str | None = None) -> DerivedArtifactRecord:
    ...
```

**Formato de salida**
```json
{
  "language": "es",
  "full_text": "...",
  "segments": [
    {"segment_index": 1, "start_ms": 0, "end_ms": 2400, "text": "..."}
  ],
  "source": "openai_stt"
}
```

---

## 4.6 Paso 5 — audio features

**Input**
- `audio_ref`
- transcript opcional para apoyo en detección de pausas / fillers

**Output**
- `DerivedArtifactRecord(kind="audio_features")`

**Módulo responsable**
- `backend/comunicacion/processing/audio.py`

**Función sugerida**
```python
def extract_audio_features(*, recording: RecordingRecord, transcript_ref: str | None = None) -> DerivedArtifactRecord:
    ...
```

**Formato de salida**
```json
{
  "speech_rate_wpm": 142.5,
  "pause_segments": [
    {"start_ms": 1800, "end_ms": 2300, "duration_ms": 500, "kind": "silent_pause"}
  ],
  "filler_count": 8,
  "prosody": {
    "mean_pitch_hz": 183.1,
    "pitch_variability": 0.43,
    "energy_variability": 0.38
  }
}
```

---

## 4.7 Paso 6 — gesture analysis

### Decisión MVP
Puede quedar fuera del primer corte real, siempre que el contrato ya reserve el hueco.

**Input**
- `frame_set`
- opcionalmente `video_ref`

**Output**
- `DerivedArtifactRecord(kind="gesture_analysis")`

**Función sugerida**
```python
def analyze_gestures(*, recording: RecordingRecord, frame_set_ref: str | None = None) -> DerivedArtifactRecord:
    ...
```

**Formato de salida**
```json
{
  "presence_score_0_100": 68,
  "hand_activity_ratio": 0.42,
  "camera_engagement_ratio": 0.61,
  "notable_windows": [
    {"start_ms": 12000, "end_ms": 18000, "label": "gesto consistente"}
  ]
}
```

---

## 4.8 Paso 7 — bundle consolidado

**Input**
- `AttemptRecord`
- `RecordingRecord`
- transcript
- audio features
- visual summary opcional

**Output**
- `CommunicationFeedbackInputBundleV1`

**Módulo responsable**
- `backend/evaluacion/domains/communication/extractor.py`

**Función sugerida**
```python
def build_communication_feedback_input_bundle_v1(*, attempt_id: str, evaluation_id: str) -> CommunicationFeedbackInputBundleV1:
    ...
```

---

## 5. Contratos JSON exactos

## 5.1 `RecordingRecord`
```json
{
  "recording_id": "rec_01HXYZ",
  "attempt_id": "att_01HXYZ",
  "user_id": "iu_abc",
  "session_id": "sess_abc",
  "mime_type": "video/webm",
  "duration_ms": 92314,
  "capture_meta": {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "audio_codec": "opus",
    "video_codec": "vp9"
  },
  "storage": {
    "video_ref": "storage://tmp/rec_01HXYZ/original.webm",
    "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg"
  },
  "created_at": "2026-03-23T00:00:00Z"
}
```

## 5.2 `TranscriptArtifact`
```json
{
  "schema_version": "communication_transcript.v1",
  "recording_id": "rec_01HXYZ",
  "language": "es",
  "full_text": "...",
  "segments": [
    {
      "segment_index": 1,
      "start_ms": 0,
      "end_ms": 2400,
      "text": "Buenos días, hoy quiero..."
    }
  ],
  "source": "openai_stt"
}
```

## 5.3 `AudioFeaturesArtifact`
```json
{
  "schema_version": "communication_audio_features.v1",
  "recording_id": "rec_01HXYZ",
  "speech_rate_wpm": 142.5,
  "pause_segments": [
    {"start_ms": 1800, "end_ms": 2300, "duration_ms": 500, "kind": "silent_pause"}
  ],
  "filler_count": 8,
  "prosody": {
    "mean_pitch_hz": 183.1,
    "pitch_variability": 0.43,
    "energy_variability": 0.38
  }
}
```

## 5.4 `GestureAnalysisArtifact`
```json
{
  "schema_version": "communication_gesture_analysis.v1",
  "recording_id": "rec_01HXYZ",
  "presence_score_0_100": 68,
  "hand_activity_ratio": 0.42,
  "camera_engagement_ratio": 0.61,
  "notable_windows": [
    {"start_ms": 12000, "end_ms": 18000, "label": "gesto consistente"}
  ]
}
```

## 5.5 `CommunicationFeedbackInputBundleV1`
```json
{
  "schema_version": "communication_feedback_input_bundle.v1",
  "evaluation_id": "eval_01HXYZ",
  "session_ref": {"user_id": "iu_abc", "session_id": "sess_abc"},
  "attempt_ref": {"attempt_id": "att_01HXYZ", "recording_id": "rec_01HXYZ"},
  "domain_context": {
    "domain": "comunicacion",
    "flow_id": "comunicacion",
    "context_id": "baseline_current",
    "context_version": "1.0.0"
  },
  "recording": {
    "duration_ms": 92314,
    "video_ref": "storage://tmp/rec_01HXYZ/original.webm",
    "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg"
  },
  "transcript": {
    "language": "es",
    "full_text": "...",
    "segments": []
  },
  "audio_features": {
    "speech_rate_wpm": 142.5,
    "pause_segments": [],
    "filler_count": 8,
    "prosody": {}
  },
  "visual_features": {
    "presence_score_0_100": null,
    "hand_activity_ratio": null,
    "camera_engagement_ratio": null,
    "notable_windows": []
  }
}
```

---

## 6. Pseudocódigo de orquestación

## 6.1 Upload → persist ref

```python
# router.py
payload -> recording_service.attach_recording_to_attempt(...)

# recording_service.py
with acquire_session_execution_lock(user_id, session_id):
    attempt = repository.get_attempt(attempt_id)
    validate_attempt_belongs_to_session(attempt, user_id, session_id)
    validate_attempt_not_submitted(attempt)
    recording = repository.create_recording(...)
    repository.attach_recording(attempt_id, recording.recording_id)
    update_world_state_runtime(last_recording_id=recording.recording_id, capture_status="uploaded")
    return recording
```

## 6.2 Submit → create evaluation

```python
# evaluation_service.py
with acquire_session_execution_lock(user_id, session_id):
    attempt = repository.get_attempt(attempt_id)
    ensure attempt.recording_id exists
    mark attempt as submitted
    evaluation_job = communication_engine.create_communication_evaluation(attempt_id=attempt_id)
    repository.link_evaluation(attempt_id, evaluation_job.evaluation_id)
    update_session_runtime(latest_evaluation_id=evaluation_job.evaluation_id, report_status=evaluation_job.status)
    return evaluation_job
```

## 6.3 Evaluation job → derivados → bundle → evaluadores → report

```python
# communication_engine/service.py
load attempt + recording
poster = ensure_poster_frame(recording)
transcript = ensure_transcript(recording)
audio_features = ensure_audio_features(recording, transcript)
visual_features = ensure_visual_features(recording)  # MVP: puede devolver vacío/placeholder
bundle = build_communication_feedback_input_bundle_v1(...)
content_output = run_content_evaluator(bundle)
delivery_output = run_delivery_evaluator(bundle)
visual_output = run_visual_evaluator(bundle)  # MVP: tolerar salida mínima
report = assemble_communication_ui_report(...)
save report
mark completed
```

---

## 7. MVP vs versión ampliada

| Artefacto | MVP | Fase ampliada | Comentario |
|---|---:|---:|---|
| `RecordingRecord` | Sí | Sí | imprescindible |
| poster frame | Recomendado | Sí | útil para UI/report |
| transcript | Sí | Sí | imprescindible |
| audio features básicas | Sí | Sí | speech rate / pausas mínimas |
| frame set completo | No | Sí | aplazar si complica pipeline |
| gesture analysis fina | No | Sí | fuera de MVP |
| bundle consolidado | Sí | Sí | imprescindible |
| visual summary placeholder | Sí | Sí | permite contrato estable desde el inicio |

### Decisión MVP optimizada
El MVP no debe exigir frame extraction compleja ni gesture scoring sofisticado. Debe arrancar con:
- transcript,
- audio features básicas,
- media block,
- report renderizable,
- y hueco contractual para visual features futuras.

---

## 8. Recomendación final del bloque

El pipeline interno debe diseñarse alrededor de **entidades persistibles pequeñas + derivados versionados + bundle estable**, no alrededor de un gran blob mutable en sesión. El primer corte implementable de `comunicacion` puede ser muy manejable si se limita a transcript + audio features básicas y deja la capa visual avanzada como una ampliación compatible, no como prerrequisito del MVP.
