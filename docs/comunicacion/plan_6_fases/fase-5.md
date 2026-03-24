# Fase 5 — Informe final, renderer y exportables

## 1. Objetivo de la fase

Fijar el informe final de `comunicacion` como un artefacto autocontenido, legible por el usuario y exportable para sistemas externos. Esta fase debe dejar cerrados:
- el contrato `UiCommunicationReportV1`,
- el assembler,
- el renderer,
- la exportación HTML/JSON/PNG,
- y la experiencia final **vídeo + evaluación**.

## 2. Por qué va en este orden

Va después de Fase 4 porque el assembler y el renderer necesitan un bundle y unas salidas de evaluadores ya estabilizadas. Va antes de Fase 6 porque el `final_result` lógico debe empaquetar un informe ya definitivo.

## 3. Archivos nuevos a crear

```text
backend/evaluacion/
  engine/
    communication_report_assembler.py
backend/comunicacion_app/
  report_view.js
  styles.css
```

Si se prefiere separar utilidades:

```text
backend/comunicacion/
  report_models.py
```

## 4. Archivos actuales a tocar

- `backend/comunicacion/models.py` si se exponen respuestas `GET report`
- `backend/comunicacion/api/router.py`
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/report_view.js`
- `backend/comunicacion_app/styles.css`

## 5. Cambios exactos por archivo

### `backend/evaluacion/engine/communication_report_assembler.py`
Responsabilidad:
- transformar bundle + outputs de evaluadores en `UiCommunicationReportV1`
- incluir explícitamente bloque `media`
- generar recomendaciones, timeline y provenance

### `backend/comunicacion_app/report_view.js`
Responsabilidad:
- `renderCommunicationReport(report, options)`
- `serializeCommunicationReportToHtml(report)`
- `captureCommunicationReportPngDataUrl(report, options)`
- `buildCommunicationReportSnapshotMarkup(report)`

### `backend/comunicacion_app/styles.css`
Responsabilidad:
- layout superior del informe
- grid de dos columnas o una columna responsive
- contenedor del vídeo pequeño fijado arriba
- reglas de impresión/captura para snapshot

## 6. Funciones / clases / modelos

### Contrato exacto del report

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
    "duration_ms": 92314,
    "player_hint": {
      "placement": "top_right",
      "size": "small",
      "sticky_within_report": true
    }
  },
  "video_panel": {
    "title": "Tu grabación",
    "help_text": "Reproduce tu vídeo mientras lees la evaluación para contrastar cada observación.",
    "default_mode": "embedded_small_player"
  },
  "block_cards": [],
  "timeline": {"segments": []},
  "recommendations": {"items": []},
  "provenance": {
    "flow_id": "comunicacion",
    "context_id": "baseline_current",
    "context_version": "1.0.0",
    "bundle_hash": "sha256:..."
  }
}
```

### Layout propuesto

```text
┌─────────────────────────────────────────────────────────────┐
│ Header del informe                                          │
├───────────────────────────────┬─────────────────────────────┤
│ Resumen / score / highlights  │ Vídeo pequeño del usuario   │
│                               │ (reproductor persistente)   │
├───────────────────────────────┴─────────────────────────────┤
│ Bloques de evaluación                                      │
├─────────────────────────────────────────────────────────────┤
│ Timeline / momentos clave                                  │
├─────────────────────────────────────────────────────────────┤
│ Recomendaciones finales                                    │
└─────────────────────────────────────────────────────────────┘
```

**Decisión cerrada de UX**: el reproductor va en la parte superior principal del informe, ocupando un panel pequeño pero siempre visible al comenzar la lectura. No queda como idea abstracta; forma parte del contrato, del renderer y del layout.

### Funciones exactas del assembler

```python
def assemble_communication_report(
    *,
    bundle: CommunicationFeedbackInputBundleV1,
    content_output: dict[str, Any],
    delivery_output: dict[str, Any],
    visual_output: dict[str, Any],
) -> dict[str, Any]: ...
```

```python
def build_report_media_block(bundle: CommunicationFeedbackInputBundleV1) -> dict[str, Any]: ...
```

### Funciones exactas del renderer

```javascript
function renderCommunicationReport(report, options = {}) {}
function renderCommunicationVideoPanel(media, panel) {}
function renderCommunicationTimeline(timeline) {}
function serializeCommunicationReportToHtml(report) {}
async function captureCommunicationReportPngDataUrl(report, options = {}) {}
```

## 7. Contratos JSON

### `GET /api/comunicacion/evaluations/{evaluation_id}/report`
```json
{
  "schema_version": "ui_communication_report.v1",
  "evaluation_id": "eval_01HXYZ",
  "header": {"report_title": "Evaluación de tu comunicación oral"},
  "media": {
    "recording_id": "rec_01HXYZ",
    "video_ref": "storage://tmp/rec_01HXYZ/original.webm",
    "poster_frame_ref": "storage://tmp/rec_01HXYZ/poster.jpg",
    "duration_ms": 92314,
    "player_hint": {"placement": "top_right", "size": "small", "sticky_within_report": true}
  },
  "video_panel": {
    "title": "Tu grabación",
    "help_text": "Reproduce tu vídeo mientras lees la evaluación para contrastarla.",
    "default_mode": "embedded_small_player"
  },
  "block_cards": [],
  "timeline": {"segments": []},
  "recommendations": {"items": []},
  "provenance": {"flow_id": "comunicacion", "context_id": "baseline_current"}
}
```

### Shape exportable del informe
```json
{
  "report_json": {"schema_version": "ui_communication_report.v1"},
  "summary_html": "<section>...</section>",
  "report_snapshot_png_data_url": "data:image/png;base64,..."
}
```

## 8. Snippets de código orientativos

### Assembler
```python
def build_report_media_block(bundle):
    return {
        'recording_id': bundle.attempt_ref['recording_id'],
        'video_ref': bundle.recording['video_ref'],
        'poster_frame_ref': bundle.recording.get('poster_frame_ref'),
        'duration_ms': bundle.recording['duration_ms'],
        'player_hint': {
            'placement': 'top_right',
            'size': 'small',
            'sticky_within_report': True,
        },
    }
```

### Renderer del panel de vídeo
```javascript
function renderCommunicationVideoPanel(media, panel) {
  return `
    <section class="comm-report-video-panel">
      <h2>${escapeHtml(panel.title)}</h2>
      <p>${escapeHtml(panel.help_text)}</p>
      <video class="comm-report-video" controls preload="metadata" poster="${escapeHtml(media.poster_frame_ref || '')}">
        <source src="${escapeHtml(media.video_ref)}" />
      </video>
    </section>
  `;
}
```

### Export HTML
```javascript
function serializeCommunicationReportToHtml(report) {
  const markup = buildCommunicationReportSnapshotMarkup(report);
  return `<!doctype html><html><head><meta charset="utf-8"></head><body>${markup}</body></html>`;
}
```

## 9. Tests recomendados

1. `backend/tests/test_communication_report_contract.py`
   - valida `UiCommunicationReportV1`
   - exige bloque `media`
   - exige `video_panel`

2. `backend/tests/test_communication_report_renderer.py`
   - renderiza vídeo pequeño arriba del informe
   - serializa HTML válido

3. `backend/tests/test_communication_report_export_contract.py`
   - exporta JSON, HTML y PNG placeholder/captura

4. `backend/tests/test_communication_report_api.py`
   - `GET /evaluations/{id}/report` devuelve shape esperado

## 10. Riesgos de la fase

- olvidar el vídeo en la zona superior y relegarlo a un modal o link
- intentar reciclar el renderer de negociación sin adaptación real
- dejar `video_ref` fuera del contrato final
- no diseñar snapshot/HTML desde el principio

## 11. Criterios de aceptación

- `UiCommunicationReportV1` queda completamente especificado
- el informe incluye vídeo pequeño arriba como parte obligatoria del layout
- existen exportables HTML/JSON/PNG definidos
- el renderer y el assembler están suficientemente descritos para implementarse en una fase posterior sin rediseño

## 12. Qué NO entra aún en esta fase

- persistencia externa real del snapshot o del HTML
- integración real con Moodle/cuaderno
- analítica visual avanzada
