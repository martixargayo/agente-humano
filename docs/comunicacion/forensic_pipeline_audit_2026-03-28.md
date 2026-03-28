# Auditoría forense del pipeline de feedback `/comunicacion` (2026-03-28)

## 1) Resumen ejecutivo

- **LLMs activas en el flujo actual**: 5 rutas LLM reales.
  1. Contenido AIDA (`communication_content_evaluator.py`)
  2. Delivery/audio (`communication_delivery_evaluator.py`)
  3. Visual batch por lotes (`communication_visual_batch_runner.py` + `communication_visual_openai_client.py`)
  4. Visual synthesis final de gesticulación (`communication_visual_synthesizer.py`)
  5. Síntesis global final (`communication_synthesis.py`)
- **Modelo configurado para todas**: `gpt-4.1-mini`.
- **Todas las llamadas LLM van con `responses.create` + `json_schema strict: true`**.
- **La LLM final (`global_synthesis`) recibe outputs ya mapeados de ramas** (no solo raw especializado): recibe `content_output`, `delivery_output`, `visual_output` completos y `evidence_summary` derivado.
- **El frontend no renderiza literalmente todos los campos del report**: consume sobre todo `header`, `block_cards`, `recommendations.items`, `media`; ignora gran parte de `global_synthesis_meta`, `branch_runtime_meta`, `provenance`, `exports.report_json`, y además **aplasta AIDA** en 4 cards derivadas de `block_cards` por índice.

---

## 2) Mapa completo del flujo (Nivel 1→6)

## Nivel 1 — LLM raw contract

### LLM #1: Contenido (AIDA)
- **Archivo evaluador**: `backend/evaluacion/engine/communication_content_evaluator.py`
- **Prompt**: `backend/evaluacion/prompts/communication_content_evaluator_prompt.txt`
- **Función carga prompt**: `_load_content_prompt_template()`
- **Input builder**: `_build_content_llm_input(bundle, content_rubric)`
- **Invocación LLM**: `_run_content_llm_openai(prompt, payload)`
- **Modelo**: `get_content_llm_model()` → `gpt-4.1-mini`
- **Schema validación raw**: `CommunicationContentAidaEvalV1`
- **Output raw esperado (estricto)**:
```json
{
  "attention": {"score_1_3": 1, "label": "mal", "reason_short": "..."},
  "interest": {"score_1_3": 2, "label": "mejorable", "reason_short": "..."},
  "development": {"score_1_3": 3, "label": "correcto", "reason_short": "..."},
  "action": {"score_1_3": 2, "label": "mejorable", "reason_short": "..."}
}
```
- **Restricción crítica**: `label` debe corresponder exactamente a `score_1_3` (validator).

### LLM #2: Delivery/audio
- **Archivo evaluador**: `backend/evaluacion/engine/communication_delivery_evaluator.py`
- **Prompt**: `backend/evaluacion/prompts/communication_delivery_evaluator_prompt.txt`
- **Carga prompt**: `load_delivery_prompt_template()`
- **Input builder**: `build_delivery_llm_input(audio_features, transcript_excerpt)`
- **Invocación LLM**: `_run_audio_specialized_eval_openai(prompt, payload)`
- **Modelo**: `get_delivery_llm_model()` → `gpt-4.1-mini`
- **Schema raw**: `CommunicationSpecializedDimensionEvalV1`
- **Output raw esperado**:
```json
{
  "score_1_5": 4,
  "label": "medio-alto",
  "reason_short": "..."
}
```

### LLM #3: Visual batch (N lotes)
- **Archivos**:
  - orquestación: `backend/evaluacion/engine/communication_visual_batch_runner.py`
  - cliente OpenAI: `backend/evaluacion/engine/communication_visual_openai_client.py`
- **Prompt**: `backend/evaluacion/prompts/communication_visual_batch_evaluator_prompt.txt`
- **Input builder**:
  - lotes: `build_visual_batch_inputs_from_manifest(...)`
  - multimodal payload: `_build_multimodal_input_for_batch(batch_input, developer_prompt)`
- **Invocación LLM**: `run_visual_batch_openai(...)`
- **Modelo**: `get_visual_openai_model()` → `gpt-4.1-mini`
- **Schema raw**: `CommunicationVisualBatchEvalV2`
- **Output raw esperado**: objeto batch muy estricto con score, sufficiency, strengths/weaknesses, flags de observabilidad y `frame_coverage_summary`.

### LLM #4: Visual synthesis (agrega lotes)
- **Archivo**: `backend/evaluacion/engine/communication_visual_synthesizer.py`
- **Prompt**: `backend/evaluacion/prompts/communication_visual_synthesis_prompt.txt`
- **Input builder**: `build_visual_synthesis_input(...)`
- **Invocación**: `run_visual_synthesis_openai(...)`
- **Modelo**: `get_visual_openai_model()` → `gpt-4.1-mini`
- **Schema raw**: `CommunicationSpecializedDimensionEvalV1`
- **Output raw esperado**:
```json
{"score_1_5": 3, "label": "medio", "reason_short": "..."}
```

### LLM #5: Global synthesis final
- **Archivo**: `backend/evaluacion/engine/communication_synthesis.py`
- **Prompt**: `backend/evaluacion/prompts/communication_global_synthesis_prompt.txt`
- **Input builder**:
  - struct: `build_global_synthesis_input(...)` → `CommunicationGlobalSynthesisInputV1`
  - payload final al modelo: `_build_synthesis_llm_payload(synthesis_input)`
- **Invocación**: `_run_global_synthesis_llm_openai(prompt, payload)`
- **Modelo**: `get_global_synthesis_llm_model()` → `gpt-4.1-mini`
- **Schema raw**: `CommunicationGlobalSynthesisLlmOutputV1`
- **Output raw esperado**:
```json
{
  "score_global_100": 84,
  "summary_short_2_3_lines": "...",
  "recommendations": [{"title": "...", "description": "..."}]
}
```

---

## Nivel 2 — Branch evaluation output (output mapeado por rama)

## Rama contenido (`evaluate_communication_content`)
- Devuelve directamente output de `evaluate_content_from_transcript`.
- **Mapeo** `_map_aida_eval_to_content_output`:
  - calcula `score_0_100` desde promedio AIDA (1..3) y lo fuerza mínimo 55.
  - compone `strengths/weaknesses/recommendations/details/evidence_segments`.
  - inyecta `llm_specialized_evaluation` con el AIDA raw completo.
- Luego añade `runtime_meta` y ajusta `summary/status_visual` según transcript real vs placeholder.

### Shape rama contenido (mapeado)
```json
{
  "block_id": "contenido",
  "title": "Contenido",
  "status_visual": "correcto|mejorable|placeholder",
  "score_0_100": 0,
  "summary": "...",
  "details": ["..."],
  "strengths": ["..."],
  "weaknesses": ["..."],
  "recommendations": ["..."],
  "evidence_segments": [{"segment_index": 1, "start_ms": 0, "end_ms": 1000, "text_excerpt": "..."}],
  "llm_specialized_evaluation": {"attention": {...}, "interest": {...}, "development": {...}, "action": {...}},
  "runtime_meta": {"branch_id": "contenido", "mode": "llm|fallback|placeholder", "reason": "...", "detail": "..."}
}
```

## Rama delivery (`evaluate_communication_delivery`)
- Ejecuta LLM specialized (o fallback) y luego mapea con `_map_specialized_to_delivery_eval` a `CommunicationDeliveryEvaluationV1`.
- Después construye bloque común para report.

### Shape rama delivery (mapeado)
```json
{
  "block_id": "delivery",
  "title": "Delivery",
  "status_visual": "correcto|mejorable|placeholder",
  "score_0_100": 0,
  "summary": "...",
  "details": ["evidence_metrics...", "observations..."],
  "subscores": {"fluency": 1, "pause_control": 1, "expressiveness": 1, "stability": 1},
  "recommendations": ["..."],
  "llm_specialized_evaluation": {"score_1_5": 3, "label": "medio", "reason_short": "..."},
  "runtime_meta": {"branch_id": "delivery", "mode": "llm|fallback|placeholder", "reason": "...", "detail": "..."}
}
```

## Rama visual (`evaluate_communication_visual`)
- Si policy `llm_v1` y hay features reales:
  - batch LLM → list `CommunicationVisualBatchEvalV2`
  - synthesis LLM visual final → `CommunicationSpecializedDimensionEvalV1`
  - agrega todo a `CommunicationVisualEvaluationV1`
- Si falla, cae a metadata evaluator.

### Shape rama visual (mapeado)
```json
{
  "block_id": "visual",
  "title": "Visual",
  "status_visual": "correcto|mejorable|placeholder",
  "score_0_100": 0,
  "summary": "...",
  "details": ["..."],
  "subscores": {"batch_quality": 1, "gesticulation_global": 1, "evidence_consistency": 1, "coverage": 1},
  "recommendations": ["..."],
  "evidence_frames": ["frame_001"],
  "visual_mode": "metadata|llm_v1",
  "llm_batch_evaluations": [/* batch raw */],
  "llm_final_evaluation": {"score_1_5": 3, "label": "medio", "reason_short": "..."},
  "llm_specialized_evaluation": {"score_1_5": 3, "label": "medio", "reason_short": "..."},
  "runtime_meta": {"branch_id": "visual", "mode": "llm|fallback|metadata|placeholder", "reason": "...", "detail": "..."}
}
```

---

## Nivel 3 — Synthesis input (payload exacto de la LLM final)

## Qué entra
La LLM final recibe **bloques de rama ya mapeados**, no solo raw especializados.

`_build_synthesis_llm_payload` envía exactamente:
```json
{
  "evaluation_id": "eval_x",
  "content_evaluation": { /* content_output completo */ },
  "delivery_evaluation": { /* delivery_output completo */ },
  "visual_evaluation": { /* visual_output completo */ },
  "evidence_summary": [
    "content_score=.. status=..",
    "delivery_score=.. status=..",
    "visual_score=.. status=..",
    "content_detail=...",
    "content_detail=...",
    "delivery_detail=...",
    "delivery_detail=...",
    "visual_detail=...",
    "visual_detail=..."
  ]
}
```

### Conclusiones forenses sobre lo que recibe la final
- **Sí recibe `score_0_100`** de cada rama (dentro de cada `*_evaluation`).
- **No recibe explícitamente `score_1_3`/`score_1_5` salvo que ya estén embebidos en `llm_specialized_evaluation` dentro de cada rama.**
- **Sí recibe `reason_short` solo indirectamente** (si está en `llm_specialized_evaluation` o dentro de `details/recommendations`).
- **Sí recibe `details/checks/recommendations` previas** porque se envía el bloque completo.
- **Sí recibe runtime/meta de rama** (va embebido en cada output rama).
- **No recibe transcript/media refs directos**, salvo lo que ya esté textualizado en summaries/details/evidence.
- **Sí recibe placeholders** (vía `status_visual='placeholder'`, summaries y runtime_meta).

---

## Nivel 4 — Synthesis output (LLM final)

## Contrato tipado
`CommunicationGlobalSynthesisLlmOutputV1`:
- `score_global_100`: int 0..100 (obligatorio)
- `summary_short_2_3_lines`: str min 1 (obligatorio)
- `recommendations`: list[0..4] de `{title, description}` (obligatorio)

`_finalize_llm_output`:
- normaliza resumen a un único párrafo,
- recorta recomendaciones a máximo 4.

### Ejemplo válido (de tests)
```json
{
  "score_global_100": 84,
  "summary_short_2_3_lines": "Has construido una comunicación bastante sólida y clara, con varios aciertos visibles, aunque aún puedes afinar el cierre.",
  "recommendations": [
    {
      "title": "Haz el cierre más intencional",
      "description": "Termina con una idea final más clara para reforzar el mensaje principal."
    }
  ]
}
```

---

## Nivel 5 — Report contract (`/report`)

Assembler: `assemble_communication_report(...)` en `communication_report_assembler.py`.

## Campos que compone
- `header`
- `media`
- `video_panel`
- `block_cards` (3: contenido, delivery, visual)
- `timeline`
- `key_moments`
- `recommendations`
- `global_synthesis`
- `global_synthesis_meta`
- `branch_runtime_meta`
- `provenance`
- `exports` (`report_json`, `summary_html`, `report_snapshot_png_data_url`)
- `placeholders`

### Reglas clave de acoplamiento
- `header.score_global_100` usa `global_synthesis.score_global_100` si existe.
- `header.summary_2_3_lines` prioriza `global_synthesis.summary_short_2_3_lines`.
- `recommendations` visibles se construyen desde `global_synthesis.recommendations` si existen.
- `block_cards` se generan de los outputs de rama (`summary/details/status/score`).

---

## Nivel 6 — Rendered feedback (frontend real)

`backend/comunicacion_app/report_view.js` consume:
- `payload.header.report_title`
- `payload.header.activity_name`
- `payload.header.stars_0_5`
- `payload.header.score_global_100`
- `payload.header.summary_2_3_lines`
- `payload.media` (`poster_frame_ref`, `playback_url`, `video_ref`, `mime_type`, `recording_id`)
- `payload.recommendations.items`
- `payload.block_cards`

## Qué hace realmente la plantilla
- “Resumen inmediato”:
  - `why` = `header.summary_2_3_lines`
  - `good` y `improve` los deriva de `block_cards` + 1ª recomendación.
- “AIDA cards”:
  - no usa AIDA raw;
  - toma `block_cards[0..3]` por **índice** y los renombra `Atención/Interés/Desarrollo/Acción`.
  - Como el backend envía 3 bloques (`contenido/delivery/visual`), la cuarta card cae en fallback.
- Entonación/Gestos:
  - busca keywords en `block_cards` y `recommendations`, no campos dedicados fuertes.

---

## 3) Input exacto por LLM (payloads)

## Contenido — payload exacto
Fuente: `_build_content_llm_input`.
```json
{
  "evaluation_id": "eval_123",
  "transcript": {
    "status": "ready|placeholder|unknown",
    "language": "es",
    "full_text": "...",
    "segments": [ /* hasta 12 segmentos model_dump */ ]
  },
  "content_rubric": { /* JSON cargado de communication_content_aida_rubric.json */ }
}
```

## Delivery — payload exacto
Fuente: `build_delivery_llm_input`.

### modo placeholder
```json
{
  "mode": "placeholder",
  "status": "placeholder",
  "explanation": "...",
  "transcript_excerpt": "..."
}
```

### modo real
```json
{
  "mode": "real",
  "status": "ready|unavailable",
  "raw_metrics": { /* CommunicationAudioRawMetricsV1 */ },
  "interpreted_metrics": { /* CommunicationAudioInterpretedMetricsV1 */ },
  "quality_flags": ["..."],
  "provider_meta": {"...": "..."},
  "transcript_excerpt": "..."
}
```

## Visual batch — payload exacto
Fuente: `_build_multimodal_input_for_batch`.

Parte JSON enviada en `input_text`:
```json
{
  "evaluation_id": "eval_x",
  "recording_id": "rec_x",
  "batch_index": 1,
  "total_batches": 3,
  "video_duration_ms": 120000,
  "sampling_strategy": {"mode":"uniform_1fps_capped_90", "candidate_fps":1, "max_frames":90, "selection":"uniform_full_duration", "batch_target":30, "tail_merge_threshold":6},
  "rubric": {"hand_use":"...", "facial_expression":"...", "posture_openness":"...", "visual_support":"..."},
  "frame_coverage_summary_hint": {"frames_total": 30, "frames_usable": 24},
  "frames": [{"frame_id":"frame_001","timestamp_ms":1000,"detail":"low"}]
}
```
Además envía cada imagen como `input_image` con `image_url=data:image/jpeg;base64,...`.

## Visual synthesis — payload exacto
Fuente: `build_visual_synthesis_input`.
```json
{
  "evaluation_id": "eval_x",
  "recording_id": "rec_x",
  "video_duration_ms": 120000,
  "batch_count": 3,
  "batch_outputs": [ /* cada item: CommunicationVisualBatchEvalV2 completo */ ]
}
```

## Global synthesis — payload exacto
Fuente: `_build_synthesis_llm_payload` sobre `CommunicationGlobalSynthesisInputV1`.
```json
{
  "evaluation_id": "eval_x",
  "content_evaluation": { /* output rama contenido completo */ },
  "delivery_evaluation": { /* output rama delivery completo */ },
  "visual_evaluation": { /* output rama visual completo */ },
  "evidence_summary": ["..."]
}
```

---

## 4) Output exacto por LLM + uso real posterior

## Contenido (AIDA)
- **Raw/tipado**: `CommunicationContentAidaEvalV1` (4 bloques AIDA).
- **Mapeado rama**: se convierte a bloque único `contenido` con `score_0_100`, `summary`, `details`, etc.
- **Se usa de verdad**:
  - score/status/summary/details para `block_cards` y síntesis global.
  - `llm_specialized_evaluation` viaja pero frontend no lo renderiza directamente.
- **Se pierde/aplana**:
  - granularidad por bloque AIDA desaparece visualmente; frontend la “reconstruye” artificialmente por índice de `block_cards`.

## Delivery
- **Raw/tipado**: `CommunicationSpecializedDimensionEvalV1` (1 score 1..5 + label + reason).
- **Mapeado rama**: a `CommunicationDeliveryEvaluationV1` (score_0_100, subscores, evidence_metrics...).
- **Se usa de verdad**:
  - `score_0_100/summary/details/recommendations` en block card y síntesis global.
- **Se pierde/aplana**:
  - `label` raw (bajo/medio...) no se muestra directamente; queda embebido en `llm_specialized_evaluation`.

## Visual batch
- **Raw/tipado**: `CommunicationVisualBatchEvalV2` por lote.
- **Mapeado rama**: agregado a un `CommunicationVisualEvaluationV1` global + arrays `llm_batch_evaluations`.
- **Se usa de verdad**:
  - score global agregado, observaciones y recomendaciones para block visual y síntesis.
- **Se pierde/aplana**:
  - detalle profundo batch (flags, coverage por lote) no se renderiza en UI principal.

## Visual synthesis
- **Raw/tipado**: `CommunicationSpecializedDimensionEvalV1`.
- **Mapeado rama**: se mezcla en score visual final (si existe) y en recomendaciones/observaciones.
- **Se usa**: `score_1_5` influye en `score_0_100` visual agregado.
- **Se pierde**: el objeto raw no tiene sección visible dedicada.

## Global synthesis
- **Raw/tipado**: `CommunicationGlobalSynthesisLlmOutputV1`.
- **Mapeado**: `_finalize_llm_output` normaliza resumen y recorta recomendaciones.
- **Se usa de verdad**:
  - `score_global_100` → header score.
  - `summary_short_2_3_lines` → header summary.
  - `recommendations[]` → recommendations visibles.
- **No usado directamente en frontend**:
  - `global_synthesis_meta` solo para diagnóstico, no bloque visual específico.

---

## 5) Qué consume exactamente la plantilla/report

## header (visible)
- `header.report_title`
- `header.activity_name`
- `header.stars_0_5`
- `header.score_global_100`
- `header.summary_2_3_lines`

## block_cards (visible)
- `title`
- `score_0_100`
- `block_verdict|summary`
- `status_visual`

## recommendations (visible)
- `recommendations.items[].title`
- `recommendations.items[].description`
- `recommendations.items[].example?.better_rephrase`

## key_moments/timeline/global_synthesis
- En esta vista JS concreta, `timeline`, `key_moments` y `global_synthesis` no tienen sección rica dedicada; el resumen/global se refleja vía `header` y recomendaciones.

## media
- usa `playback_url` preferente, fallback `video_ref`, y `poster_frame_ref`.

---

## 6) Legacy/sobrante/aplanado (forense)

1. **`CommunicationVisualFinalEvalV1`** existe en contratos pero en este flujo no es el contrato usado por la síntesis visual actual (se usa `CommunicationSpecializedDimensionEvalV1`).
2. **`llm_specialized_evaluation`** en ramas viaja completo, pero la UI no lo explota explícitamente.
3. **AIDA real se aplana**: backend produce un bloque `contenido`; frontend inventa 4 tarjetas AIDA desde `block_cards` por índice.
4. **`branch_runtime_meta`, `global_synthesis_meta`, `provenance`** son útiles para observabilidad/auditoría, casi no visibles para usuario final.
5. **`exports.report_json`** se genera completo, pero la vista principal no lo usa para render; se usa más para export/entrega.
6. **`details` se truncan indirectamente en síntesis**: `build_global_synthesis_input` solo toma hasta 2 detalles por rama para `evidence_summary`.

---

## 7) Puntos de control para futuros ajustes (sin cambiar comportamiento ahora)

- Si quieres mejorar calidad final percibida: primer cuello es **acoplamiento frontend↔backend**, especialmente AIDA (cards por índice).
- Si quieres mejorar coherencia de síntesis final: revisar **qué subset exacto de cada rama entra a `evidence_summary`** vs bloque completo.
- Si quieres trazabilidad LLM-to-UI: exponer en UI los campos de `llm_specialized_evaluation` y/o `llm_batch_evaluations`.
- Si quieres reducir ruido/legacy: decidir si mantener contratos no utilizados en runtime (ej. `CommunicationVisualFinalEvalV1`).

