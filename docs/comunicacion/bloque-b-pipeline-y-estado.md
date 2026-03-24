# Bloque B — Pipeline de datos y estado interno

## 1. Resumen ejecutivo del bloque

El flujo `comunicacion` requiere un pipeline de datos esencialmente distinto del de `negociacion`: ya no parte de un historial conversacional por turnos, sino de una **grabación audiovisual** y de artefactos derivados heterogéneos. El repositorio actual sí ofrece un patrón valioso para construir bundles, jobs y reports, pero ese patrón está diseñado alrededor de un input exclusivamente textual/conversacional (`FeedbackInputBundleV1`, `ConversationBlock`, `BundleTurn`, `TurnTrajectoryV1`).

La propuesta es introducir una cadena de estado explícita y trazable:
1. `recording` bruto,
2. artefactos derivados (`frames`, `audio_features`, `transcript`),
3. bundle consolidado de evaluación,
4. evaluadores especializados por aspecto,
5. ensamblado final del report.

La clave de diseño es que cada módulo consuma **solo la vista de datos que necesita**, evitando acoplar todo el pipeline a un blob único y opaco.

## 2. Estado actual del repo relevante para este bloque

### 2.1 Contratos actuales de evaluación
`backend/evaluacion/contracts/models.py` define un sistema de contratos cerrado sobre negociación:
- `FeedbackInputBundleV1` contiene `conversation`, `conversation_stats`, `domain_context`, `derived_facts`, `trace_digest`.
- `DomainContext` fija `domain: Literal["negociacion"]`.
- `CoreRunnerInputV1` y `TrajectoryRunnerInputV1` esperan conversación por turnos.
- El report final se expresa como bloques + trayectoria de turnos.

Diagnóstico: esta estructura no puede representar de forma natural una grabación con media, timestamps, features visuales ni segmentos temporales no conversacionales.

### 2.2 Extractor actual de negociación
`backend/evaluacion/domains/negotiation/extractor.py` demuestra bien el patrón actual:
- toma `SessionState`,
- empareja `history` en turnos user/assistant,
- calcula stats básicas,
- deriva señales heurísticas,
- deriva contexto y trazas,
- y monta el bundle.

Esto es útil como patrón de ensamblado, pero no sirve como extractor base de `comunicacion`.

### 2.3 Job engine actual
`backend/evaluacion/engine/service.py` ya modela el ciclo de vida asíncrono:
- creación de job,
- `building_inputs`,
- ejecución de varios evaluadores,
- ensamblado de report,
- guardado de latencias y hashes de provenance.

Esto sí debe reaprovecharse como esqueleto conceptual.

### 2.4 Repositorio y metadatos de jobs
`backend/evaluacion/storage/models.py` y `backend/evaluacion/storage/in_memory_repository.py` ya guardan:
- `status`,
- `error`,
- `stage_latencies_ms`,
- `artifacts`.

Esto es especialmente útil para `comunicacion`, porque va a necesitar registrar muchos artefactos derivados sin que todos formen parte del report final.

## 3. Qué reutilizar del código actual

### 3.1 `FeedbackJobRecord.artifacts`
El campo `artifacts: dict[str, str]` es una buena referencia, pero previsiblemente se quedará corto si se quieren registrar estructuras complejas de media. Sirve como base de diseño para:
- hashes,
- refs de storage,
- estado de preprocesado,
- IDs correlativos.

### 3.2 `create_evaluation(...)` / `_run_pipeline_from_bundle(...)`
El engine actual separa muy bien:
- construcción de inputs,
- ejecución de evaluadores,
- reconciliación,
- ensamblado.

Ese patrón es el que debe copiar `comunicacion`, incluso si el contenido de los stages cambia.

### 3.3 `Provenance`
El objeto `Provenance` actual es muy valioso como idea:
- hashes de bundle/input/output,
- modelos usados,
- versiones de prompt,
- identidad de flow/context.

Para `comunicacion` conviene extenderlo o crear una variante que añada referencias a recording y derivados.

## 4. Qué habría que crear nuevo

## 4.1 Modelo de `recording`
Propuesta mínima:

```json
{
  "recording_id": "rec_01H...",
  "attempt_id": "att_01H...",
  "session_ref": {
    "user_id": "u_...",
    "session_id": "sess_..."
  },
  "flow_id": "comunicacion",
  "context_id": "baseline_current",
  "capture": {
    "mime_type": "video/webm",
    "video_codec": "vp9",
    "audio_codec": "opus",
    "duration_ms": 92314,
    "width": 1280,
    "height": 720,
    "fps": 30
  },
  "storage": {
    "original_video_ref": "storage://.../original.webm",
    "poster_frame_ref": "storage://.../poster.jpg"
  },
  "created_at": "2026-03-23T00:00:00Z"
}
```

### Responsabilidad sugerida
Este modelo debe vivir fuera de `SessionState` pesado. La sesión debería guardar solo referencias e IDs, no blobs ni base64 de media.

## 4.2 Modelo de artefactos derivados
Propuesta de tres familias separadas:

### a) Visual derivatives
```json
{
  "recording_id": "rec_x",
  "frame_set": {
    "strategy": "uniform_plus_activity_peaks",
    "frame_count": 24,
    "frames": [
      {"frame_index": 12, "timestamp_ms": 400, "image_ref": "storage://.../f0012.jpg"}
    ]
  },
  "visual_summary": {
    "face_detected_ratio": 0.94,
    "hands_visible_ratio": 0.61,
    "shot_stability_score": 0.88,
    "notes": []
  }
}
```

### b) Audio derivatives
```json
{
  "recording_id": "rec_x",
  "audio_track": {
    "audio_ref": "storage://.../audio.wav",
    "duration_ms": 92314,
    "sample_rate_hz": 16000
  },
  "timing_features": {
    "speech_rate_wpm": 142.5,
    "pause_segments": [
      {"start_ms": 1800, "end_ms": 2300, "duration_ms": 500, "kind": "silent_pause"}
    ],
    "voiced_ratio": 0.71,
    "filler_count": 8
  },
  "prosody_features": {
    "mean_pitch_hz": 183.1,
    "pitch_variability": 0.43,
    "energy_variability": 0.38
  }
}
```

### c) Transcript derivatives
```json
{
  "recording_id": "rec_x",
  "transcript": {
    "language": "es",
    "full_text": "...",
    "segments": [
      {"segment_index": 1, "start_ms": 0, "end_ms": 3400, "text": "..."}
    ],
    "source": "openai_stt"
  },
  "content_features": {
    "estimated_topic_coverage": ["apertura", "idea_central", "cierre"],
    "keyword_hits": ["mensaje", "objetivo"],
    "lexical_diversity": 0.57
  }
}
```

## 4.3 Nuevo bundle consolidado de evaluación
Propuesta: `CommunicationFeedbackInputBundleV1`.

```json
{
  "schema_version": "communication_feedback_input_bundle.v1",
  "evaluation_id": "eval_x",
  "session_ref": {"user_id": "u", "session_id": "s"},
  "attempt_ref": {"attempt_id": "att_x", "recording_id": "rec_x"},
  "domain_context": {
    "domain": "comunicacion",
    "flow_id": "comunicacion",
    "context_id": "baseline_current",
    "context_version": "1.0.0"
  },
  "recording": {
    "duration_ms": 92314,
    "video_ref": "storage://.../original.webm",
    "poster_frame_ref": "storage://.../poster.jpg"
  },
  "transcript": {
    "full_text": "...",
    "segments": []
  },
  "audio_features": {
    "speech_rate_wpm": 142.5,
    "pause_segments": [],
    "prosody_features": {}
  },
  "visual_features": {
    "frame_refs": [],
    "gesture_windows": [],
    "presence_features": {}
  },
  "processing_trace": {
    "transcript_source": "openai_stt",
    "visual_pipeline_version": "v0",
    "audio_pipeline_version": "v0"
  }
}
```

## 5. Propuesta de organización

## 5.1 Nuevos módulos backend sugeridos

```text
backend/comunicacion/storage/models.py
backend/comunicacion/storage/repository.py
backend/comunicacion/processing/video.py
backend/comunicacion/processing/audio.py
backend/comunicacion/processing/transcript.py
backend/evaluacion/domains/communication/extractor.py
backend/evaluacion/contracts/communication_models.py
```

### Responsabilidades
- `storage/models.py`: entidades persistentes (`RecordingRef`, `AttemptRecord`, `DerivedArtifactRef`).
- `storage/repository.py`: lookup y actualización de refs/estado.
- `processing/video.py`: extracción de poster, frames y ventanas visuales.
- `processing/audio.py`: extracción de wav, pausas, prosodia, features temporales.
- `processing/transcript.py`: STT y segmentación temporal.
- `extractor.py`: construir el bundle consolidado desde refs persistidas.
- `communication_models.py`: contratos tipados del dominio.

## 5.2 Estado interno sugerido de sesión
La sesión no debe almacenar el vídeo; solo metadatos activos.

Bloque sugerido en `world_state`:

```json
{
  "communication_runtime": {
    "active_attempt_id": "att_x",
    "last_recording_id": "rec_x",
    "latest_evaluation_id": "eval_x",
    "capture_status": "uploaded",
    "review_status": "pending_submission"
  }
}
```

### Motivo
Esto replica el patrón de `negotiation_canonical`, pero con semántica mínima y sin meter artefactos pesados en sesión.

## 5.3 Estado interno sugerido de job
El job actual usa `JobStatus` demasiado corto para media. Para `comunicacion` tendría sentido un set más granular:

```json
[
  "created",
  "queued",
  "extracting_video",
  "extracting_audio",
  "transcribing",
  "building_inputs",
  "running_content_eval",
  "running_delivery_eval",
  "running_visual_eval",
  "running_timeline_eval",
  "assembling_report",
  "completed",
  "failed"
]
```

## 6. Contratos de datos o schemas sugeridos

## 6.1 Attempt record
```json
{
  "attempt_id": "att_123",
  "user_id": "u_123",
  "session_id": "sess_123",
  "context_id": "baseline_current",
  "status": "draft",
  "created_at": "2026-03-23T00:00:00Z",
  "updated_at": "2026-03-23T00:00:00Z",
  "recording_id": null,
  "latest_evaluation_id": null,
  "rerecord_count": 0
}
```

## 6.2 Derived artifact reference
```json
{
  "artifact_id": "art_123",
  "recording_id": "rec_123",
  "kind": "transcript|audio_features|frame_set|visual_summary|poster_frame",
  "version": "v1",
  "storage_ref": "storage://bucket/key.json",
  "content_hash": "sha256:...",
  "created_at": "2026-03-23T00:00:00Z"
}
```

## 6.3 Evaluator input slices
### Content evaluator input
```json
{
  "schema_version": "communication_content_input.v1",
  "evaluation_id": "eval_x",
  "domain_context": {"domain": "comunicacion"},
  "transcript": {"full_text": "...", "segments": []},
  "content_features": {}
}
```

### Delivery evaluator input
```json
{
  "schema_version": "communication_delivery_input.v1",
  "evaluation_id": "eval_x",
  "audio_features": {"speech_rate_wpm": 142.5, "pause_segments": [], "prosody_features": {}}
}
```

### Visual evaluator input
```json
{
  "schema_version": "communication_visual_input.v1",
  "evaluation_id": "eval_x",
  "frame_set": {"frames": []},
  "visual_summary": {}
}
```

## 7. Rutas, funciones, clases o módulos concretos que servirían de base

### Base conceptual actual
- `backend/evaluacion/domains/negotiation/extractor.py::build_feedback_input_bundle_v1`
- `backend/evaluacion/engine/service.py::_run_pipeline_from_bundle`
- `backend/evaluacion/storage/models.py::FeedbackJobRecord`
- `backend/evaluacion/storage/in_memory_repository.py::patch_job_metadata`
- `backend/sessions/state.py::SessionState`

### Nuevas firmas sugeridas
```python
# backend/evaluacion/domains/communication/extractor.py

def build_communication_feedback_input_bundle_v1(*, attempt_id: str, evaluation_id: str) -> CommunicationFeedbackInputBundleV1:
    ...

# backend/comunicacion/processing/transcript.py

def transcribe_recording(*, recording_ref: str, language_hint: str | None = None) -> TranscriptArtifactV1:
    ...

# backend/comunicacion/processing/audio.py

def extract_audio_features(*, recording_ref: str) -> AudioFeaturesArtifactV1:
    ...

# backend/comunicacion/processing/video.py

def extract_visual_artifacts(*, recording_ref: str) -> VisualArtifactsV1:
    ...
```

## 8. Riesgos y decisiones pendientes

### Riesgo: falta de storage binario
El repositorio solo tiene storage de sesión y feedback en memoria/Redis. No existe aún storage de vídeos, frames ni jsons derivados. Esto es la principal pieza ausente para que `comunicacion` sea trazable y revisualizable.

### Riesgo: `artifacts: dict[str, str]` puede quedarse pequeño
Sirve como telemetría ligera, pero no como modelo robusto de pipeline multimedia. Seguramente hará falta una entidad aparte para `AttemptRecord` / `RecordingRecord` / `DerivedArtifactRecord`.

### Riesgo: sesiones sobrecargadas
Guardar demasiada información derivada en `world_state` haría crecer el envelope y complicaría persistencia/rehidratación. La recomendación es guardar solo referencias resumidas.

### Decisión pendiente: origen de transcript y features
Queda por decidir si el pipeline guarda siempre:
- transcript raw,
- transcript normalized,
- features raw,
- features agregadas,
- o una mezcla.

El diagnóstico recomienda conservar **artefacto raw + resumen normalizado**, porque eso facilita recalcular scoring sin reingestar vídeo.

## 9. Recomendación final del bloque

`comunicacion` necesita una capa de datos explícita que el repo hoy no tiene: **recordings + derived artifacts + bundles multimodales**. La arquitectura más limpia es mantener la sesión ligera, persistir media y derivados fuera de la sesión, y construir bundles especializados por evaluador. El pipeline actual de `evaluacion` es una muy buena base estructural, pero no debe reutilizarse sin introducir contratos independientes para el nuevo dominio.
