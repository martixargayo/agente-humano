# Fase 4 — Evaluación mínima y pipeline de job

## 1. Objetivo de la fase

Definir el pipeline mínimo de evaluación para que un `attempt` con `recording` pueda producir un `evaluation_id`, pasar por estados de job trazables y acabar generando un report básico útil para el MVP.

## 2. Por qué va en este orden

Va después de Fase 3 porque la app ya sabe crear attempt, subir recording y pedir submit. Va antes del renderer final porque primero hay que cerrar qué produce el pipeline: transcript, audio features, visual placeholder y bundle consolidado.

## 3. Archivos nuevos a crear

```text
backend/comunicacion/
  services/
    evaluation_service.py
backend/evaluacion/
  contracts/
    communication_models.py
  engine/
    communication_service.py
    communication_bundle_builder.py
    communication_assembler.py
    communication_evaluators.py
  domains/
    communication/
      __init__.py
      extractor.py
      context_resolver.py
```

## 4. Archivos actuales a tocar

- `backend/comunicacion/api/router.py`
- `backend/comunicacion/models.py`
- `backend/comunicacion/services/recording_service.py` si se documenta mejor el acceso a artefactos
- `backend/evaluacion/storage/models.py` solo si hace falta reusar el repositorio actual de jobs con un campo compatible; cambio pequeño y seguro
- `backend/evaluacion/api/router.py` preferiblemente no tocar; mejor exponer todo desde router propio de `comunicacion`

## 5. Cambios exactos por archivo

### `backend/evaluacion/contracts/communication_models.py`
Definir contratos exactos:
- `CommunicationFeedbackInputBundleV1`
- `CommunicationCoreEvaluatorInput`
- `CommunicationDeliveryEvaluatorInput`
- `CommunicationVisualEvaluatorInput`
- `CommunicationEvaluationStatusResponse`

### `backend/evaluacion/engine/communication_bundle_builder.py`
Responsabilidad:
- cargar `AttemptRecord`, `RecordingRecord` y artefactos
- construir bundle consolidado para evaluadores

### `backend/evaluacion/engine/communication_evaluators.py`
Responsabilidad:
- `evaluate_communication_content(...)`
- `evaluate_communication_delivery(...)`
- `evaluate_communication_visual_placeholder(...)`

### `backend/evaluacion/engine/communication_service.py`
Responsabilidad:
- crear `evaluation_id`
- persistir job
- ejecutar pipeline mínimo
- actualizar estados `queued/running/completed/failed`

## 6. Funciones / clases / modelos

### Firmas de funciones

```python
def create_communication_evaluation(*, user_id: str, session_id: str, attempt_id: str) -> dict[str, Any]: ...
```

```python
def build_communication_feedback_input_bundle(*, evaluation_id: str, attempt_id: str) -> CommunicationFeedbackInputBundleV1: ...
```

```python
def evaluate_communication_content(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, Any]: ...
```

```python
def evaluate_communication_delivery(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, Any]: ...
```

```python
def evaluate_communication_visual_placeholder(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, Any]: ...
```

```python
def run_communication_evaluation_job(*, evaluation_id: str) -> None: ...
```

### Estados del job

```text
queued
 -> extracting
 -> transcript_ready
 -> audio_features_ready
 -> visual_placeholder_ready
 -> assembling_report
 -> completed
```

Errores terminales:
- `failed`
- `cancelled` si más adelante se necesitara, pero no es obligatorio en MVP

## 7. Contratos JSON

### `CommunicationFeedbackInputBundleV1`
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
  "transcript": {"language": "es", "full_text": "...", "segments": []},
  "audio_features": {"speech_rate_wpm": 142.5, "pause_segments": [], "filler_count": 8},
  "visual_features": {"status": "placeholder", "presence_score_0_100": null, "notable_windows": []}
}
```

### `GET /api/comunicacion/evaluations/{evaluation_id}`
```json
{
  "evaluation_id": "eval_01HXYZ",
  "attempt_id": "att_01HXYZ",
  "status": "running",
  "stage": "audio_features_ready",
  "report_available": false,
  "error": null
}
```

## 8. Snippets de código orientativos

### Pseudocódigo del pipeline
```python
def run_communication_evaluation_job(*, evaluation_id: str) -> None:
    mark_status(evaluation_id, status='running', stage='extracting')
    bundle = build_communication_feedback_input_bundle(evaluation_id=evaluation_id, attempt_id=job.attempt_id)

    transcript = extract_transcript(bundle.recording.video_ref)
    mark_status(evaluation_id, status='running', stage='transcript_ready')

    audio_features = extract_basic_audio_features(bundle.recording.video_ref, transcript)
    mark_status(evaluation_id, status='running', stage='audio_features_ready')

    visual_output = evaluate_communication_visual_placeholder(bundle)
    mark_status(evaluation_id, status='running', stage='visual_placeholder_ready')

    content_output = evaluate_communication_content(bundle)
    delivery_output = evaluate_communication_delivery(bundle)

    report = assemble_communication_report(...)
    persist_report(...)
    mark_status(evaluation_id, status='completed', stage='completed')
```

### Placeholder visual explícito
```python
def evaluate_communication_visual_placeholder(bundle):
    return {
        'status': 'placeholder',
        'score_visual_0_100': None,
        'summary': 'La evaluación visual avanzada no forma parte del MVP inicial.',
        'signals': [],
    }
```

## 9. Tests recomendados

1. `backend/tests/test_communication_bundle_builder.py`
   - construye bundle desde `attempt` + `recording`

2. `backend/tests/test_communication_evaluation_job.py`
   - crea `evaluation_id`
   - avanza por estados esperados
   - persiste report al terminar

3. `backend/tests/test_communication_visual_placeholder.py`
   - la ausencia de analítica visual avanzada no rompe el job
   - el report sigue siendo ensamblable

4. `backend/tests/test_communication_status_api.py`
   - `GET /evaluations/{id}` devuelve estado y stage coherentes

## 10. Riesgos de la fase

- intentar resolver visual analytics avanzada demasiado pronto
- acoplar el job de `comunicacion` al engine de negociación
- persistir payloads enormes dentro del job record
- no separar bundle builder de evaluadores

## 11. Criterios de aceptación

- existe `evaluation_id` con ciclo de vida trazable
- transcript y audio features mínimas quedan representadas en contratos estables
- el hueco visual está modelado como placeholder compatible, no como bloqueo
- el router de `comunicacion` ya puede crear evaluación y consultar estado

## 12. Qué NO entra aún en esta fase

- renderer visual final del informe
- export HTML/PNG
- bridge final con Moodle
- scoring visual avanzado
