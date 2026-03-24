# Bloque D — Informe final / ensamblado de feedback

## 1. Resumen ejecutivo del bloque

El sistema actual de feedback ya resuelve muy bien la última milla: transformar outputs técnicos de evaluación en un informe visual renderizable, exportable y transferible al contenedor embebido. No obstante, el contrato actual de report (`UiFeedbackReportV1`) y el renderer `feedback_report_view.js` están semánticamente construidos para negociación, con bloques fijos (`valores`, `vision`, `relacion`, `proceso`) y una trayectoria por turnos con score de cercanía a acuerdo.

Para `comunicacion`, la recomendación es **crear un contrato de report nuevo y un assembler específico**, reutilizando la estructura general del sistema actual: header, bloques, timeline, momentos clave, recomendaciones y provenance. El vídeo grabado debe convertirse en parte explícita de la experiencia de resultado, no en mero adjunto externo.

## 2. Estado actual del repo relevante para este bloque

### 2.1 Assembler actual
`backend/evaluacion/engine/assembler.py` construye `UiFeedbackReportV1` con:
- `header`,
- `block_cards`,
- `trajectory_chart`,
- `key_moments`,
- `recommendations`,
- `provenance`.

La arquitectura es muy buena como referencia: mantiene la UI desacoplada del detalle de ejecución y recibe un objeto ya listo para render.

### 2.2 Report view actual
`backend/interfaz_usuario_app/feedback_report_view.js` organiza la experiencia de informe en:
- cabecera con score/estrellas,
- resultado textual,
- tarjetas por bloque,
- gráfico SVG de trayectoria,
- tooltips por turno,
- recomendaciones.

Esto proporciona una base visual sólida que puede adaptarse para `comunicacion`.

### 2.3 Report final y embed
El frontend actual serializa el report a HTML/JSON/PNG, lo muestra en pantalla y lo empaqueta para `final_result`. Esto es especialmente útil si `comunicacion` necesita entregar al cuaderno tanto el informe como una snapshot exportable del mismo.

## 3. Qué reutilizar del código actual

### 3.1 `assemble_ui_report(...)` como patrón
La función actual demuestra que conviene aislar el ensamblado final en una capa dedicada. Para `comunicacion`, debería existir algo análogo, por ejemplo:

```python
# backend/evaluacion/engine/communication_assembler.py

def assemble_communication_ui_report(*, core, timeline, media, provenance) -> UiCommunicationReportV1:
    ...
```

### 3.2 `feedback_report_view.js` como librería base de diseño
Se puede reutilizar:
- layout general por cards,
- estilo de score/stars,
- patrón de gráfico temporal,
- sistema de exportación,
- serializer HTML/PNG.

### 3.3 `Provenance`
Debe mantenerse el principio de provenance completa. En `comunicacion` se debería ampliar con:
- `recording_id`,
- hash de transcript,
- hash de audio features,
- hash de visual features,
- versionado del pipeline de media.

## 4. Qué habría que crear nuevo

## 4.1 Nuevo contrato de report visual
Propuesta: `UiCommunicationReportV1`.

```json
{
  "schema_version": "ui_communication_report.v1",
  "evaluation_id": "eval_x",
  "header": {
    "report_title": "Evaluación de tu comunicación oral",
    "activity_name": "Presentación breve grabada",
    "score_global_100": 78,
    "stars_0_5": 3.9,
    "summary_2_3_lines": "Transmites bien la idea principal, pero puedes ganar claridad en pausas y cierre."
  },
  "media": {
    "recording_id": "rec_x",
    "video_ref": "storage://.../original.webm",
    "poster_frame_ref": "storage://.../poster.jpg",
    "duration_ms": 92314
  },
  "block_cards": [],
  "timeline": [],
  "key_moments": {},
  "recommendations": {"items": []},
  "provenance": {}
}
```

## 4.2 Bloques de evaluación sugeridos
Recomendación de bloques renderizables y estables a futuro:
- `contenido`
- `claridad`
- `tono_y_voz`
- `pausas_y_ritmo`
- `comunicacion_no_verbal`

### Motivo
Estos bloques son suficientemente generales para permitir iterar criterios internos después, sin rehacer toda la arquitectura de report ni el renderer.

## 4.3 Timeline / segmentación temporal
En `comunicacion` no conviene una trayectoria por turnos. La representación más útil sería una de estas dos:

### Opción A — Segmentos temporales uniformes
- dividir en ventanas de 10–15 segundos,
- score general por ventana,
- flags de eventos.

### Opción B — Segmentos semánticos
- apertura,
- desarrollo,
- cierre,
- y subsegmentos internos si aplica.

Diagnóstico: la arquitectura debe soportar ambas. La timeline debería modelarse como lista de segmentos genéricos, no como `turn_index`.

Ejemplo de schema:
```json
{
  "segments": [
    {
      "segment_id": "seg_1",
      "label": "Apertura",
      "start_ms": 0,
      "end_ms": 18000,
      "score_0_100": 74,
      "summary": "Inicio claro pero algo acelerado.",
      "signals": ["buen contacto visual", "ritmo alto"]
    }
  ]
}
```

## 5. Propuesta de organización

## 5.1 Nuevos contratos en backend

```text
backend/evaluacion/contracts/communication_models.py
  - CommunicationEvaluationBlock
  - CommunicationTimelineSegment
  - CommunicationKeyMoment
  - CommunicationRecommendationItem
  - CommunicationProvenance
  - UiCommunicationReportV1
```

## 5.2 Nuevo assembler

```text
backend/evaluacion/engine/communication_assembler.py
```

### Responsabilidad
Traducir outputs especializados de evaluadores de contenido/audio/visual/timeline a un único payload renderizable por frontend.

## 5.3 Nuevo renderer frontend

```text
backend/comunicacion_app/report_view.js
```

### Responsabilidad
- renderizar vídeo + informe en una misma vista,
- pintar timeline clicable,
- permitir saltar a segmentos relevantes del vídeo,
- exportar HTML/PNG/JSON.

## 6. Contratos de datos o schemas sugeridos

## 6.1 Block card
```json
{
  "block_id": "tono_y_voz",
  "title": "Tono y voz",
  "status_visual": "mejorable",
  "score_0_100": 64,
  "checks": [
    {
      "polarity": "check",
      "micro_explanation": "Tu volumen se mantiene estable durante casi toda la intervención.",
      "evidence_segment_ids": ["seg_2"]
    },
    {
      "polarity": "cross",
      "micro_explanation": "La entonación cae demasiado al cerrar la idea final.",
      "evidence_segment_ids": ["seg_5"]
    }
  ],
  "block_verdict": "voz estable pero con poca variación expresiva"
}
```

## 6.2 Key moments
```json
{
  "best_moment": {
    "segment_id": "seg_2",
    "label": "Desarrollo inicial",
    "why": "Aquí explicas con más claridad y energía tu idea principal.",
    "impact": "Aumenta la comprensión y la sensación de seguridad."
  },
  "most_delicate_moment": {
    "segment_id": "seg_5",
    "label": "Cierre",
    "why": "El final pierde fuerza y concreción.",
    "impact": "Reduce el impacto final del mensaje."
  },
  "turning_point": {
    "segment_id": "seg_3",
    "label": "Mitad de la exposición",
    "why": "A partir de aquí mejoras el ritmo y la mirada a cámara.",
    "impact": "La intervención gana naturalidad."
  }
}
```

## 6.3 Media block
```json
{
  "recording_id": "rec_x",
  "video_ref": "storage://.../original.webm",
  "poster_frame_ref": "storage://.../poster.jpg",
  "waveform_ref": "storage://.../waveform.json",
  "duration_ms": 92314
}
```

## 7. Cómo encajarlo con el sistema de report actual

## 7.1 Estrategia recomendada
No reemplazar `UiFeedbackReportV1`; crear una variante paralela.

### Por qué
- Mantiene intacto el flujo `negociacion`.
- Evita if/else por `activity_type` en todo el renderer actual.
- Permite que `comunicacion` evolucione con widgets nuevos (player de vídeo, markers en timeline, thumbnails por segmento).

## 7.2 Reaprovechamiento de API de exportación
Sí conviene reaprovechar la filosofía de:
- `serializeReportToHtml`
- `downloadReportHtml`
- `downloadReportJson`
- `downloadReportPng`

Pero probablemente en un módulo nuevo o en un renderer extendido con namespace separado.

## 7.3 Video + informe en la misma experiencia
Recomendación:
- pantalla final con layout a dos columnas o stack responsive,
- player de vídeo arriba/izquierda,
- report a derecha/debajo,
- clic en segmento del report → `seek()` del vídeo,
- clic en marcador temporal del vídeo → mostrar detalle del segmento.

Esto requiere que el report incluya referencias temporales (`start_ms`, `end_ms`).

## 8. Rutas, funciones, clases o módulos concretos que servirían de base

### Referencias actuales
- `backend/evaluacion/engine/assembler.py::assemble_ui_report`
- `backend/interfaz_usuario_app/feedback_report_view.js::renderChart`
- `backend/interfaz_usuario_app/feedback_report_view.js::tooltipMarkup`
- `backend/interfaz_usuario_app/feedback_report_view.js::downloadReportPng`
- `backend/tests/test_public_interfaz_usuario_serving.py`
- `backend/tests/test_embed_final_result_contract.py`

### Nuevas firmas sugeridas
```python
# backend/evaluacion/engine/communication_assembler.py

def assemble_communication_ui_report(*, summary, block_scores, timeline, recommendations, media, provenance) -> UiCommunicationReportV1:
    ...
```

```javascript
// backend/comunicacion_app/report_view.js
function renderCommunicationReport(root, report) {}
function serializeCommunicationReportToHtml(report) {}
async function captureCommunicationReportPngDataUrl(report, options = {}) {}
```

## 9. Riesgos y decisiones pendientes

### Riesgo: renderer demasiado rígido si se fija ya una rúbrica fina
Conviene que el contrato de report soporte evolución. Por eso los bloques deben ser genéricos y versionados, y la timeline debe expresarse con segmentos, no con un tipo hiper específico.

### Riesgo: dependencia de reproducción de vídeo
Si el `video_ref` no es resoluble en frontend de forma segura, la experiencia quedará partida entre informe y media. Esto debe resolverse a nivel de storage delivery antes de implementar.

### Riesgo: exportación PNG/HTML con vídeo
El vídeo no se rasteriza igual que un DOM estático. El export del informe debe asumir que el PNG representa el report, no necesariamente un frame reproducible del vídeo.

### Decisión pendiente: report unificado o doble vista
Queda por decidir si la UX final presenta:
- un solo layout vídeo+feedback,
- o una pestaña “Vídeo” y otra “Informe”.

La arquitectura recomendada soporta ambas, siempre que el contrato `media` y la timeline temporal estén presentes.

## 10. Recomendación final del bloque

El sistema actual de feedback ofrece una base muy sólida para `comunicacion`, pero la adaptación correcta es por **paralelismo de contratos**, no por reutilización literal del report de negociación. Debe existir un assembler y un renderer específicos, capaces de representar una evaluación multimodal centrada en vídeo, sin perder las ventajas ya logradas por el sistema actual: informe elegante, exportable, versionado y compatible con embed/Moodle.
