# 04 — Evaluación y report

## 1. Resumen ejecutivo

La evaluación de `comunicacion` debe apoyarse en el patrón fuerte que ya existe en `backend/evaluacion/engine/service.py`, pero con contratos totalmente nuevos. La recomendación MVP es separar cuatro piezas:

1. **Content evaluator**
2. **Delivery evaluator** (voz/pausas)
3. **Visual evaluator** (gesticulación/presencia), tolerante a modo MVP básico
4. **Assembler final**

Este diseño mantiene el job engine legible, permite evolucionar cada aspecto de forma independiente y evita mezclar la semántica de negociación (`agreement_reached`, `turn_index`, bloques `valores/vision/relacion/proceso`) con la nueva actividad.

---

## 2. Contratos nuevos exactos

## 2.1 `CommunicationFeedbackInputBundleV1`

```json
{
  "schema_version": "communication_feedback_input_bundle.v1",
  "evaluation_id": "eval_01HXYZ",
  "session_ref": {
    "user_id": "iu_abc",
    "session_id": "sess_abc"
  },
  "attempt_ref": {
    "attempt_id": "att_01HXYZ",
    "recording_id": "rec_01HXYZ"
  },
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
    "full_text": "Buenos días, hoy quiero presentar...",
    "segments": [
      {"segment_index": 1, "start_ms": 0, "end_ms": 2400, "text": "Buenos días..."}
    ]
  },
  "audio_features": {
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
  },
  "visual_features": {
    "presence_score_0_100": 68,
    "hand_activity_ratio": 0.42,
    "camera_engagement_ratio": 0.61,
    "notable_windows": [
      {"start_ms": 12000, "end_ms": 18000, "label": "gesto consistente"}
    ]
  }
}
```

## 2.2 `CommunicationCoreEvaluatorInput`

**Propósito**
- evaluar contenido global y estructura.

```json
{
  "schema_version": "communication_core_evaluator_input.v1",
  "evaluation_id": "eval_01HXYZ",
  "domain_context": {
    "domain": "comunicacion",
    "flow_id": "comunicacion",
    "context_id": "baseline_current",
    "context_version": "1.0.0"
  },
  "transcript": {
    "full_text": "...",
    "segments": []
  },
  "recording_meta": {
    "duration_ms": 92314
  }
}
```

## 2.3 `CommunicationDeliveryEvaluatorInput`

**Propósito**
- evaluar voz, pausas y ritmo.

```json
{
  "schema_version": "communication_delivery_evaluator_input.v1",
  "evaluation_id": "eval_01HXYZ",
  "audio_features": {
    "speech_rate_wpm": 142.5,
    "pause_segments": [],
    "filler_count": 8,
    "prosody": {}
  },
  "transcript_segments": []
}
```

## 2.4 `CommunicationVisualEvaluatorInput`

**Propósito**
- evaluar comunicación no verbal.

```json
{
  "schema_version": "communication_visual_evaluator_input.v1",
  "evaluation_id": "eval_01HXYZ",
  "visual_features": {
    "presence_score_0_100": 68,
    "hand_activity_ratio": 0.42,
    "camera_engagement_ratio": 0.61,
    "notable_windows": []
  },
  "recording_meta": {
    "duration_ms": 92314,
    "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg"
  }
}
```

## 2.5 `UiCommunicationReportV1`

```json
{
  "schema_version": "ui_communication_report.v1",
  "evaluation_id": "eval_01HXYZ",
  "header": {
    "report_title": "Evaluación de tu comunicación oral",
    "activity_name": "Presentación breve grabada",
    "score_global_100": 74,
    "stars_0_5": 3.7,
    "summary_2_3_lines": "Tu mensaje principal se entiende, pero puedes mejorar el cierre y la gestión de pausas."
  },
  "media": {
    "recording_id": "rec_01HXYZ",
    "video_ref": "storage://tmp/rec_01HXYZ/original.webm",
    "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg",
    "duration_ms": 92314
  },
  "block_cards": [
    {
      "block_id": "contenido",
      "title": "Contenido",
      "status_visual": "correcto",
      "score_0_100": 78,
      "checks": [
        {
          "polarity": "check",
          "micro_explanation": "La idea principal se entiende con claridad.",
          "evidence_segment_ids": ["seg_2"]
        }
      ],
      "block_verdict": "contenido claro pero con cierre mejorable"
    }
  ],
  "timeline": {
    "segments": [
      {
        "segment_id": "seg_1",
        "label": "Apertura",
        "start_ms": 0,
        "end_ms": 18000,
        "score_0_100": 70,
        "summary": "Inicio correcto aunque algo acelerado.",
        "signals": ["inicio directo", "ritmo alto"]
      }
    ]
  },
  "key_moments": {
    "best_moment": {
      "segment_id": "seg_2",
      "label": "Desarrollo inicial",
      "why": "Aquí tu explicación es más clara y estable.",
      "impact": "Mejora la comprensión del mensaje."
    },
    "most_delicate_moment": {
      "segment_id": "seg_5",
      "label": "Cierre",
      "why": "La conclusión pierde fuerza.",
      "impact": "Reduce el impacto final."
    },
    "turning_point": {
      "segment_id": "seg_3",
      "label": "Mitad de la exposición",
      "why": "A partir de aquí estabilizas el ritmo.",
      "impact": "La intervención gana naturalidad."
    }
  },
  "recommendations": {
    "items": [
      {
        "title": "Haz más visible tu cierre",
        "description": "Termina con una frase final más concreta y una pausa de cierre.",
        "example": {
          "original_excerpt": "Y bueno, eso sería todo.",
          "better_rephrase": "En resumen, esta es la idea clave que quiero que recordéis."
        }
      }
    ]
  },
  "provenance": {
    "evaluation_id": "eval_01HXYZ",
    "recording_id": "rec_01HXYZ",
    "bundle_hash": "sha256:...",
    "core_output_hash": "sha256:...",
    "delivery_output_hash": "sha256:...",
    "visual_output_hash": "sha256:...",
    "flow_id": "comunicacion",
    "context_id": "baseline_current",
    "context_version": "1.0.0"
  }
}
```

---

## 3. Separación de evaluadores

## 3.1 MVP concreto recomendado

| Evaluador | Entra en MVP | Input | Output |
|---|---:|---|---|
| contenido | Sí | transcript + context | resumen global + score de contenido |
| voz/pausas | Sí | audio features + transcript segments | score delivery + observaciones |
| gesticulación | Parcial | visual summary mínima | score básico o placeholder compatible |
| timeline | Sí | transcript segments + audio features | segmentos temporales + scores |
| assembler final | Sí | salidas previas + media block | `UiCommunicationReportV1` |

## 3.2 Qué entra a cada evaluador

### a) Content evaluator
**Input**
- transcript completa
- segmentos
- metadatos de duración/contexto

**Sale**
- `score_contenido_0_100`
- resumen 2–3 líneas
- recomendaciones de mensaje/estructura

**Modelo esperado**
- LLM textual estructurado

### b) Delivery evaluator
**Input**
- speech rate
- pause segments
- fillers
- prosody básica
- transcript segmentada

**Sale**
- score `tono_y_voz`
- score `pausas_y_ritmo`
- observaciones por ventanas o segmentos

**Modelo esperado**
- LLM textual sobre features ya calculadas

### c) Visual evaluator
**Input**
- visual summary
- notable windows
- poster/frame set opcional

**Sale**
- score `comunicacion_no_verbal`
- hallazgos de presencia/mirada/gesto

**Modelo esperado**
- en MVP, puede ser heurístico o LLM sobre features agregadas; no obliga todavía a VLM complejo

### d) Timeline evaluator
**Input**
- transcript segments
- audio features
- visual notable windows opcional

**Sale**
- segmentos temporales con `score_0_100`, `summary`, `signals`

---

## 4. Job engine

## 4.1 Estados propuestos

```text
created
queued
extracting_audio
transcribing
analyzing_audio
analyzing_visual
building_inputs
running_content_eval
running_delivery_eval
running_visual_eval
assembling_report
completed
failed
```

## 4.2 Cómo encaja con el engine actual

### Referencia real
`backend/evaluacion/engine/service.py` ya hace:
- `_set_status(...)`
- `_patch(...)`
- `_run_pipeline_from_bundle(...)`
- `_launch_pipeline_task(...)`

### Propuesta recomendada
No tocar ese archivo al principio. Crear un paralelo:

```text
backend/evaluacion/engine/communication_service.py
```

con helpers equivalentes:
```python
def create_communication_evaluation(*, attempt_id: str) -> FeedbackJobRecord: ...
def get_communication_evaluation_status(*, evaluation_id: str) -> FeedbackJobRecord: ...
def get_communication_evaluation_report(*, evaluation_id: str) -> UiCommunicationReportV1: ...
```

### Ventaja
- evita romper negociación,
- permite iterar job states propios,
- mantiene un patrón de implementación familiar.

---

## 5. Assembler

## 5.1 Archivo nuevo propuesto

```text
backend/evaluacion/engine/communication_assembler.py
```

## 5.2 Firma exacta sugerida

```python
from evaluacion.contracts.communication_models import UiCommunicationReportV1


def assemble_communication_ui_report(
    *,
    core_summary: dict,
    delivery_summary: dict,
    visual_summary: dict,
    timeline_summary: dict,
    media_block: dict,
    provenance: dict,
) -> UiCommunicationReportV1:
    ...
```

## 5.3 Responsabilidad
- calcular score global final,
- traducir salidas parciales a block cards,
- construir timeline,
- construir key moments,
- construir recommendations,
- incluir media block y provenance.

---

## 6. Renderer

## 6.1 Qué parte de `feedback_report_view.js` sirve de base

### Reutilizable
- estructura por cards,
- estilos base,
- render de score y estrellas,
- serializers HTML/JSON/PNG,
- patrón de gráfico temporal SVG,
- export buttons/helpers.

### A rehacer
- `BLOCK_LABELS` de negociación,
- tooltips por turno,
- copy orientada a acuerdo,
- cálculo visual basado en `agreement_closeness_score_0_100`.

## 6.2 API mínima de `report_view.js`

```javascript
function renderCommunicationReport(root, report) {}
function serializeCommunicationReportToHtml(report) {}
function serializeCommunicationReportToJson(report) {}
async function captureCommunicationReportPngDataUrl(report, options = {}) {}
async function downloadCommunicationReportPng(report, options = {}) {}
```

## 6.3 Integración del vídeo dentro del informe

### Decisión recomendada
El report debe incluir un bloque `media` con:
- `video_ref`
- `poster_frame_ref`
- `duration_ms`

Y el renderer debe:
- crear un `<video controls>` usando `video_ref`,
- superponer o listar markers de timeline,
- permitir `seek()` al hacer click en segmentos.

---

## 7. Snippets orientativos

## 7.1 Modelos Pydantic sugeridos

```python
from pydantic import BaseModel, ConfigDict, Field


class CommunicationSessionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    session_id: str


class CommunicationAttemptRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str
    recording_id: str


class CommunicationTimelineSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment_id: str
    label: str
    start_ms: int
    end_ms: int
    score_0_100: int
    summary: str
    signals: list[str] = Field(default_factory=list)
```

## 7.2 Assembler orientativo

```python

def assemble_communication_ui_report(...):
    score_global = int(round((core_summary["score"] + delivery_summary["score"] + visual_summary["score"]) / 3))
    return UiCommunicationReportV1(
        schema_version="ui_communication_report.v1",
        evaluation_id=provenance["evaluation_id"],
        header={
            "report_title": "Evaluación de tu comunicación oral",
            "activity_name": core_summary.get("activity_name", "Actividad de comunicación"),
            "score_global_100": score_global,
            "stars_0_5": round(score_global / 20.0, 1),
            "summary_2_3_lines": core_summary["summary_2_3_lines"],
        },
        media=media_block,
        block_cards=[...],
        timeline=timeline_summary,
        key_moments={...},
        recommendations={"items": [...]},
        provenance=provenance,
    )
```

## 7.3 Renderer orientativo

```javascript
function renderCommunicationReport(root, report) {
  root.innerHTML = `
    <section class="comm-report">
      <div class="comm-header"></div>
      <div class="comm-media-and-summary"></div>
      <div class="comm-blocks"></div>
      <div class="comm-timeline"></div>
      <div class="comm-recommendations"></div>
    </section>
  `;
  renderHeader(root.querySelector('.comm-header'), report.header);
  renderVideo(root.querySelector('.comm-media-and-summary'), report.media);
  renderBlocks(root.querySelector('.comm-blocks'), report.block_cards);
  renderTimeline(root.querySelector('.comm-timeline'), report.timeline, report.media);
  renderRecommendations(root.querySelector('.comm-recommendations'), report.recommendations);
}
```

---

## 8. Recomendación final del bloque

La evaluación de `comunicacion` debe organizarse desde el principio como un pipeline de evaluadores especializados sobre un bundle estable, con un assembler paralelo al actual. El MVP no necesita perfeccionar todavía la multimodalidad visual; sí necesita fijar contratos limpios y un renderer capaz de mostrar el vídeo y el informe en una única experiencia coherente.
