# Diagnóstico de confidence en world_buckets (v3, LLM-first)

## 1) Lifecycle end-to-end (diseño esperado)

```text
Contrato (schemas/defaults)
  -> Extractor v4 (prompt pide confidence + parser normaliza)
    -> Merge append-mostly (_normalize_bucket_item + dedupe)
      -> Normalización canónica (normalize_world_buckets)
        -> Consumo (top_evidence_v2 / ranking visual / gates indirectos)
          -> Telemetría (extractor_meta -> trace_item -> build_trace_event -> LiveTrace)
```

### Escrituras/lecturas clave
- **Contrato/base v3**: `default_world_state().world_state_meta.evidence_confidence_min = 0.6`. Hoy está en metadata, no aplicado como filtro en `top_evidence_v2`.  
- **Extractor v4**:
  - Prompt define item con `confidence`.
  - `_normalize_item` parsea `confidence`, clamp 0..1 y marca `confidence_defaulted`.
- **Merge**:
  - `merge_world_buckets_append_mostly` re-normaliza cada item con `_normalize_bucket_item` y dedupe por `raw_text`.
- **Normalización final**:
  - `normalize_world_buckets` vuelve a sanear tipos, confidence y flags.
- **Uso**:
  - `top_evidence_v2` ordena por `confidence`, no filtra por `evidence_confidence_min`.
- **Render**:
  - `negotiation_graph` copia `extractor_confidence_summary` desde `extractor_meta` al `debug_trace`.
  - `live_trace.build_trace_event` expone `extractor_confidence_summary` y `top_evidence_v2`.

---

## 2) Cómo funciona AHORA (antes del fix)

Hallazgo principal reproducible:
- Si el LLM emitía `"confidence": 0`, el sistema lo aceptaba como **valor explícito válido**.
- En ese caso, `confidence_defaulted` quedaba `false` (porque no faltaba ni fallaba parseo).

Esto explicaba exactamente el síntoma de LiveTrace:
- item con `confidence=0`
- `confidence_defaulted=false`
- “evidencia top” con `(0)`

---

## 3) Qué falla exactamente

### Causa raíz
**Política implícita inconsistente** entre “default 0.6” y “0 explícito se respeta”.

- El código defaulteaba a 0.6 **solo si falta confidence o no parsea**.
- Pero para `0` numérico, no defaulteaba.
- Por eso nunca marcaba `confidence_defaulted=true` en esos casos.

### Por qué esto rompe el sistema
- Introduce evidencia con score 0 “válida”, degradando ranking.
- Hace inútil cualquier interpretación de `evidence_confidence_min=0.6` si no hay filtro posterior.
- Incoherencia semántica: “confidence baja/ausente” vs “0 explícito pero no defaulted”.

---

## 4) Decisión de diseño recomendada

### Semántica
Para `world_buckets`, **confidence = confianza de extracción/fidelidad del claim al texto del usuario** (no “relevancia de planner”).

### Política
- Rango válido: `[0,1]`.
- `0` en extracción de bucket item se trata como **missing/invalid para operación** (en v3 actual), porque en práctica degrada toda la cadena.
- LLM **debe emitir** confidence.
- Si falta / no parsea / `<=0`: default `0.6`, `confidence_defaulted=true`.
- Strings/NaN/out-of-range: parse+clamp, y en fallo default 0.6.

---

## 5) Fix mínimo aplicado

1. **Prompt extractor v4 reforzado**
   - confidence obligatorio.
   - numeric [0,1].
   - instrucción explícita de no emitir `0` salvo incertidumbre total.
   - sugerencia operativa: emitir items con confidence >= 0.60.

2. **Parser extractor (`_normalize_item`)**
   - `confidence<=0` ahora defaultea a 0.6.
   - marca `confidence_defaulted=true`.
   - añade `confidence_source` (`emitted_by_llm` | `defaulted_by_parser`).

3. **Normalizadores canónicos**
   - `world_state_updater._normalize_bucket_item`: misma política (`<=0` => default + defaulted + source).
   - `validation.normalize_world_buckets`: misma política (`<=0` => default + defaulted + source).

4. **Instrumentación mínima**
   - En `extractor_meta` se añade:
     - `confidence_values_emitted` (count/min/max/zeros/missing)
     - `extractor_confidence_summary` (emitted/missing/zeros/min/max/avg/per_bucket)
   - Ya se propagaba a LiveTrace vía `negotiation_graph` + `build_trace_event`; ahora viaja completo.

---

## 6) Hipótesis priorizadas (top 3) y evidencia

1. **H1 (confirmada): el LLM emite 0 y el parser lo respetaba**.
   - Resultado: `confidence=0`, `confidence_defaulted=false`.
2. **H2 (confirmada): no existía guardrail en merge/normalizer para `<=0`**.
   - Resultado: 0 sobrevivía múltiples etapas.
3. **H3 (confirmada): `top_evidence_v2` no aplica threshold de `evidence_confidence_min`**.
   - Resultado: evidencia 0 aparece en ranking visual.

---

## 7) Guardrails/tests

- Test de invariantes: no permitir combinación `confidence==0 && confidence_defaulted==false` tras merge.
- Test de fallback: si falta confidence => `defaulted=true` y `confidence>=0.6`.
- Test de extractor stats: `extractor_confidence_summary` con conteos de missing/zeros/per_bucket.

---

## 8) Notas de compatibilidad v3

- No se cambia el contrato estructural v3 de `world_buckets`.
- No se reintroduce legacy.
- Se corrige semántica operacional de confidence con cambios puntuales y trazables.
