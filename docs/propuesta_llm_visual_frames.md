# Evaluación crítica de baseline multimodal para gesticulación (OpenAI)

Fecha: 2026-03-27

## 1) Veredicto sobre la baseline propuesta
**Sí, la baseline es sólida como V1 de producción** si se implementa con guardrails explícitos:
- `<= 1 fps`
- `<= 90 frames`
- selección uniforme en toda la duración cuando `duration_s > 90`
- batching objetivo de 30 con regla de resto `<6`
- OpenAI Responses API con `detail="low"`

Crítica honesta: no es óptima en recall temporal fino, pero sí es una muy buena relación **calidad/coste/latencia/complejidad** para detectar **indicios visuales** (no biomecánica).

---

## 2) Puntos fuertes
1. **Control de coste**: cota dura de 90 frames evita explosión de tokens.
2. **Cobertura temporal**: muestreo uniforme evita sesgo a primeros segundos.
3. **Operabilidad**: lotes de 30 permiten retries parciales y mejor observabilidad.
4. **Coherencia con objetivo**: para “indicios no verbales” el `detail=low` suele ser suficiente.
5. **Integración gradual**: encaja con el pipeline actual (frame manifest + evaluator) sin romper backward compatibility.

---

## 3) Riesgos / debilidades
1. **Riesgo de submuestreo** en gestos breves entre segundos.
2. **Variación entre lotes** (batch drift): un lote puede verse muy “fuerte” y otro muy “débil”.
3. **Dependencia de encuadre**: manos fuera de cámara → falso “bajo uso de manos”.
4. **`detail=low`** puede degradar microexpresiones faciales.
5. **Sesgo por uniformidad pura**: ignora segmentos de alta dinámica.

---

## 4) Correcciones o ajustes recomendados
Sin romper decisiones baseline, recomiendo:
1. Mantener baseline exacta para V1, pero añadir **telemetría** de cobertura:
   - `visible_face_ratio`, `visible_hands_ratio`, `blurry_ratio` por batch.
2. Añadir un **confidence ceiling**:
   - si menos de X frames con rostro/cuerpo útil, cap de confianza.
3. Agregar **síntesis final con limitaciones explícitas** (no continuidad temporal).
4. Feature flag:
   - `VISUAL_EVAL_MODE=metadata|llm_v1`.

---

## 5) Diseño exacto del sampling uniforme

### Reglas funcionales
- `candidate_frames = floor(duration_ms / 1000)` con timestamps en segundos enteros `[0..candidate_frames-1]`.
- Si `candidate_frames <= 90`: usar todos.
- Si `candidate_frames > 90`: seleccionar exactamente 90 índices uniformes en `[0, candidate_frames-1]`.

### Método recomendado (sin sesgo fuerte)
Usar mapeo por centros de bin:
```python
N = candidate_frames
K = 90
# índices únicos y ordenados
idx_j = floor((j + 0.5) * N / K)  for j in [0..K-1]
idx_j = clamp(idx_j, 0, N-1)
```

Ventajas:
- distribuye sobre toda la duración;
- evita sesgo sistemático al inicio;
- garantiza `K` muestras estables.

### Edge cases
- `duration_ms < 1000`: forzar al menos 1 frame en `t=0`.
- redondeos en frontera (ej. 90.0s exacto): definir con segundos truncados consistentes (`floor`).
- deduplicación: si por rounding apareciera duplicado (raro), completar con siguiente índice libre más cercano.

---

## 6) Diseño exacto del batching

### Reglas
- Objetivo base: chunks de 30.
- Resto `r = total % 30`.
- Si `r == 0`: batches exactos de 30.
- Si `r >= 6`: batch extra con `r`.
- Si `r < 6` y `total > 30`: fusionar resto con batch anterior (`[..., 30+r]`).

### Ejemplos esperados
- 65 → 30 + 35
- 66 → 30 + 30 + 6
- 89 → 30 + 30 + 29
- 90 → 30 + 30 + 30

### Pseudocódigo
```python
def batch_frames(frames):
    chunks = [frames[i:i+30] for i in range(0, len(frames), 30)]
    if len(chunks) >= 2 and len(chunks[-1]) < 6:
        chunks[-2].extend(chunks[-1])
        chunks.pop()
    return chunks
```

---

## 7) Arquitectura propuesta en el repo

### Estado actual relevante
- Extracción: `backend/evaluacion/engine/communication_frame_extractor.py` (`extract_video_frames`).
- Sampling actual fijo: `sample_every_ms=1500`, `max_frames=12` en `backend/evaluacion/domains/communication/extractor.py`.
- Contrato frame manifest: `backend/evaluacion/contracts/communication_models.py`.
- Evaluación visual actual heurística: `backend/evaluacion/engine/communication_visual_evaluator.py`.
- Orquestación/persistencia: `backend/evaluacion/engine/communication_service.py`.

### Cambios propuestos (sin romper)
1. **Nuevo selector de frames**
   - archivo nuevo: `backend/evaluacion/engine/communication_visual_sampling.py`
   - funciones:
     - `build_1fps_candidates(manifest|video_path)`
     - `select_uniform_frames(candidates, max_frames=90)`
     - `partition_batches(frames, target=30, min_extra=6)`

2. **Extensión de extractor**
   - `communication_frame_extractor.py`:
     - soportar extracción 1fps candidatos con `max_frames=None` opcional;
     - mantener API existente para no romper callers.

3. **Transporte multimodal a OpenAI**
   - archivo nuevo: `backend/evaluacion/engine/communication_visual_openai_client.py`
   - función:
     - `evaluate_visual_batch_openai(batch_input) -> BatchEvaluation`
   - usar Responses API con `input`:
     - `input_text` + múltiples `input_image`.
   - `detail="low"` por frame.

4. **Síntesis final**
   - archivo nuevo: `backend/evaluacion/engine/communication_visual_synthesizer.py`
   - función:
     - `synthesize_visual_batches(partials, manifest_meta) -> FinalVisualEvaluation`

5. **Feature flag y fallback**
   - `communication_visual_evaluator.py`:
     - `mode=metadata|llm_v1`.
   - En `metadata`, no cambia nada.

6. **Persistencia de artefactos**
   - `communication_service.py`:
     - guardar `visual_batch_eval` por lote,
     - guardar `visual_llm_final` sintetizado.

---

## 8) Contrato input/output por lote y síntesis

### 8.1 Input por lote → LLM
```json
{
  "evaluation_id": "eval_x",
  "recording_id": "rec_x",
  "batch_index": 1,
  "total_batches": 3,
  "video_duration_ms": 180000,
  "sampling_strategy": {
    "mode": "uniform_1fps_capped_90",
    "candidate_fps": 1,
    "max_frames": 90,
    "selection": "uniform_full_duration"
  },
  "frames": [
    {
      "frame_id": "frame_001",
      "timestamp_ms": 0,
      "image_ref": "file_id_or_url",
      "detail": "low"
    }
  ],
  "rubric": {
    "hand_use": "1-5",
    "gesture_observability": "1-5",
    "facial_expressivity": "1-5",
    "posture_openness": "1-5",
    "visual_support": "1-5"
  },
  "output_schema": "communication_visual_batch_eval.v1"
}
```

### 8.2 Output parcial por lote
```json
{
  "schema_version": "communication_visual_batch_eval.v1",
  "batch_score_1_5": 4,
  "evidence_sufficiency": "medium",
  "hand_use_assessment": "Uso de manos visible en parte relevante del lote.",
  "facial_expression_assessment": "Expresividad moderada y consistente.",
  "posture_assessment": "Postura abierta la mayor parte del tiempo.",
  "strengths": ["gesticulación clara", "postura estable"],
  "weaknesses": ["poca variación facial en algunos tramos"],
  "limitations": ["manos fuera de encuadre en 4 frames"],
  "cited_frame_ids": ["frame_010", "frame_018"],
  "confidence": 0.72
}
```

### 8.3 Output final de síntesis
```json
{
  "schema_version": "communication_visual_final_eval.v1",
  "global_score_1_5": 4,
  "label": "sólido",
  "diagnosis": "Buena comunicación no verbal con áreas de mejora específicas.",
  "temporal_consistency": "medium",
  "top_strengths": ["uso de manos", "apertura corporal"],
  "top_weaknesses": ["expresividad facial irregular"],
  "recommendations": ["aumentar variación facial en cierres"],
  "evidence_frame_ids": ["frame_010", "frame_044", "frame_082"],
  "confidence": 0.69,
  "limitations": ["no se evalúa sincronía gesto-palabra"],
  "batch_summaries": []
}
```

---

## 9) Prompts propuestos

### 9.1 Prompt por lote (sistema/developer)
**Objetivo**: evaluar solo indicios observables, sin inventar continuidad.

Plantilla:
1. Rol: evaluador de comunicación no verbal basado únicamente en frames.
2. Reglas:
   - no inferir audio ni intención no visible;
   - no asumir continuidad entre frames ausentes;
   - reportar limitaciones de cobertura y encuadre;
   - citar `frame_id` como evidencia.
3. Rúbrica 1-5 para:
   - manos,
   - gesticulación observable,
   - expresividad facial,
   - postura/apertura,
   - apoyo visual.
4. Salida estricta JSON schema `communication_visual_batch_eval.v1`.

### 9.2 Prompt de síntesis final
**Objetivo**: agregar parciales sin sobreafirmar continuidad temporal.

Reglas:
- ponderar evidencia_sufficiency por lote;
- si conflicto entre lotes, declarar inconsistencia;
- confidence final <= promedio ponderado por suficiencia;
- incluir limitaciones globales.

Salida estricta JSON schema `communication_visual_final_eval.v1`.

### 9.3 Buenas prácticas OpenAI aplicadas
- Instrucciones explícitas (qué hacer / qué no hacer).
- Output estructurado con schema estricto.
- Campos con descripciones claras para facilitar eval automática.
- Diseño preparado para incorporar few-shot de calibración posterior.

---

## 10) Recomendación de modelo OpenAI

### Recomendación principal (V1)
1. **GPT-4.1-mini** (preferencia #1)
   - equilibrio bueno entre calidad de instrucción y coste;
   - soporta imagen input y Responses API.

### Alternativas
2. **GPT-4.1**
   - mejor calidad/consistencia, coste más alto.
3. **GPT-4o-mini**
   - coste muy bajo por token de texto, pero en visión tile-cost base puede dispararse según tokenización.

### Criterio práctico
- Empezar con 4.1-mini y medir:
  - estabilidad de score por reruns,
  - correlación con evaluación humana,
  - coste/latencia p95.
- Escalar a 4.1 solo si la ganancia de calidad lo justifica.

---

## 11) Riesgos y mitigaciones
1. **Frames poco representativos**
   - Mitigación: uniformidad full-duration + evidencia_sufficiency.
2. **Manos fuera de encuadre**
   - Mitigación: bandera `hand_visibility_low` + bajar confianza.
3. **Calidad insuficiente**
   - Mitigación: métricas de nitidez/iluminación previas; fallback a metadata.
4. **Sobre-inferencia del modelo**
   - Mitigación: prompt con prohibiciones explícitas + schema con `limitations` obligatorias.
5. **Variabilidad entre lotes**
   - Mitigación: síntesis con reglas deterministas de agregación.
6. **Coste/latencia**
   - Mitigación: cota 90, lotes 30, retries parciales.
7. **Sesgo por sampling**
   - Mitigación: algoritmo uniforme robusto (center-bin), no primeros 90s.

---

## 12) Plan de implementación incremental

### Fase 0 (sin riesgo)
- Agregar contratos y utilidades de sampling/batching.
- Tests unitarios de:
  - selección uniforme,
  - regla de resto `<6`.

### Fase 1 (shadow mode)
- Ejecutar rama `llm_v1` en paralelo sin impactar score oficial.
- Persistir artefactos parciales/finales.

### Fase 2 (A/B interno)
- Comparar `metadata` vs `llm_v1` con muestra manual etiquetada.
- Medir: acuerdo humano, coste, latencia p50/p95.

### Fase 3 (rollout controlado)
- Activar `llm_v1` para % de tráfico.
- Guardrail de fallback automático a `metadata` en timeout/error.

### Fase 4 (hardening)
- Few-shot de calibración por contexto.
- Evals continuas y monitoreo drift.

---

## Apéndice: referencias oficiales relevantes
- OpenAI Images & Vision (multi-image, `detail`, límites, tokenización): https://platform.openai.com/docs/guides/images-vision
- OpenAI Prompt engineering: https://platform.openai.com/docs/guides/prompt-engineering
- OpenAI Structured outputs: https://platform.openai.com/docs/guides/structured-outputs
- OpenAI Evals: https://platform.openai.com/docs/guides/evals
- OpenAI model pages (4.1 / 4.1-mini / 4o-mini):
  - https://platform.openai.com/docs/models/gpt-4.1
  - https://platform.openai.com/docs/models/gpt-4.1-mini
  - https://platform.openai.com/docs/models/gpt-4o-mini
