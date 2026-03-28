# Plan de implementación detallado — adaptación de la pantalla final de feedback `/comunicacion`

**Fecha:** 2026-03-28  
**Alcance:** plan (sin implementación de cambios de comportamiento todavía)  
**Principio rector:** cambios quirúrgicos en cableado/mappings/plantilla, manteniendo evaluadores/LLMs existentes salvo ajustes mínimos estrictamente necesarios.

---

## 1) Resumen ejecutivo corto

## Problema real hoy
El problema principal no es la existencia de LLMs ni la falta de prompts, sino el **acoplamiento incorrecto entre outputs y render final**:
- la UI reconstruye AIDA desde `block_cards` por índice en vez de usar el AIDA real;
- la sección de entrega verbal mezcla señales y no separa claramente audio vs gesticulación;
- `block_cards` actúa como fuente dominante cuando ya no representa bien la estructura objetivo;
- la vista muestra datos técnicos (`recording_id`, `video_ref`) que no aportan valor pedagógico.

## Estrategia correcta
1. **Conservar LLMs y outputs especializados** actuales como fuente de verdad.
2. **Exponer en `/report` secciones render-ready explícitas** para AIDA, audio y visual especializado.
3. **Reescribir la plantilla para renderizar por sección explícita**, no por heurísticas/índices.
4. Dejar `block_cards` como compatibilidad transitoria (secundaria), no como fuente principal de la pantalla.

## Qué NO hace falta tocar
- Arquitectura general del pipeline paralelo.
- Modelos LLM base y prompts completos.
- Flujo de síntesis global (salvo consumo en UI).

## Qué sí hay que tocar
- Contrato de `/report` orientado a UI final.
- Assembler para incluir secciones especializadas directas.
- `report_view.js` para renderizar desde fuentes correctas.
- Tests de contrato/render para blindar regressions.

---

## 2) Mapa fuente → pantalla (objetivo)

| Sección visible | Fuente correcta | Shape esperado (mínimo) | Estado actual | Cambio necesario |
|---|---|---|---|---|
| Cabecera: título | `report.header.report_title` | `string` | Ya existe | Mantener |
| Cabecera: nota global | `report.global_synthesis.score_global_100` (fallback header) | `0..100` | Existe y se usa | Mantener prioridad explícita |
| Cabecera: estrellas (sin texto “x/5”) | Código UI (derivado de nota global) | `★` visual | Hoy muestra texto `x/5` | Ajuste frontend |
| Resumen (1 párrafo) | `report.global_synthesis.summary_short_2_3_lines` | `string` | Existe pero UI añade “Lo más fuerte / Prioridad…” | Simplificar frontend |
| AIDA: Atención | `content.llm_specialized_evaluation.attention` | `{score_1_3,label,reason_short}` | Hoy se reconstruye por índice | Cambiar assembler + frontend |
| AIDA: Interés | `...interest` | idem | idem | idem |
| AIDA: Desarrollo | `...development` | idem | idem | idem |
| AIDA: Acción | `...action` | idem | hoy puede caer en fallback artificial | usar AIDA real siempre |
| Entrega verbal: Entonación y pausas | `delivery.llm_specialized_evaluation` | `{score_1_5,label,reason_short}` | Mezclado en bloques genéricos | exponer sección dedicada |
| Entrega verbal: Gesticulación | `visual.llm_specialized_evaluation` | `{score_1_5,label,reason_short}` | Mezclado/heurístico por keywords | exponer sección dedicada |
| Grabación (solo reproductor útil) | `report.media.playback_url/poster/mime_type` | video + ayuda | hoy muestra `recording_id` y `video_ref` | limpiar frontend |
| Recomendaciones (0-4) | `report.global_synthesis.recommendations` | `[{title,description}]` | ya existe | mantener; no rellenar artificial |

---

## 3) Diagnóstico del estado actual (sección por sección)

## 3.1 Cabecera
- **Bien:** score global y resumen se soportan vía `global_synthesis`.
- **Ajuste:** ocultar el texto explícito `x/5` en estrellas (dejar solo estrellas visuales).

## 3.2 Resumen
- **Bien:** existe el resumen global breve proveniente de LLM final.
- **Mal cableado:** la UI deriva “Lo más fuerte” y “Prioridad de mejora” desde `block_cards/recommendations`, desviando foco.
- **Acción:** dejar solo un párrafo de resumen global.

## 3.3 AIDA
- **Bien:** backend sí conserva AIDA especializado (`llm_specialized_evaluation` en contenido).
- **Mal cableado grave:** UI usa `resolveAidaCards(blockCards)` por índice con títulos fijos, provocando “Acción” de relleno.
- **Pérdida de información:** se ignoran `score_1_3`, `label`, `reason_short` reales.
- **Acción:** consumir AIDA real, mapear label→color semáforo, eliminar score /100 en esos cuadros.

## 3.4 Entrega verbal
- **Bien:** hay specialized eval de audio y visual disponibles en outputs de rama.
- **Mal cableado:** UI infiere entonación/gestos por búsqueda de keywords en arrays heterogéneos.
- **Acción:** crear dos secciones explícitas en report: `audio_specialized_feedback` y `visual_specialized_feedback`.

## 3.5 Grabación
- **Bien:** reproductor ya existe.
- **Mal UX:** muestra metadata técnica interna (`recording_id`, `video_ref`).
- **Acción:** dejar sólo reproductor + ayuda opcional.

## 3.6 Recomendaciones
- **Bien:** ya salen de `global_synthesis` y soportan 0..4.
- **Acción:** mantener sin rellenar por heurística.

## 3.7 Dependencia de `block_cards`
- **Estado:** útil como agregación legacy para compatibilidad/export, insuficiente como fuente principal de UI objetivo.
- **Acción:** degradar su rol a secundario, conservar temporalmente para backward compatibility.

---

## 4) Plan de cambios por archivo

## 4.1 Backend / evaluadores

### `backend/evaluacion/engine/communication_content_evaluator.py`
- **Responsabilidad actual:** evalúa AIDA y mapea a bloque contenido + `llm_specialized_evaluation`.
- **Problema actual:** ninguno crítico en producción de AIDA.
- **Cambio propuesto:** **sin cambios funcionales** (solo confirmar contrato estable).
- **Impacto esperado:** cero riesgo; AIDA sigue fuente de verdad.

### `backend/evaluacion/engine/communication_delivery_evaluator.py`
- **Responsabilidad actual:** produce specialized eval audio + mapping a delivery agregado.
- **Problema actual:** output specialized existe pero no se consume de forma explícita en UI.
- **Cambio propuesto:** opcional menor: asegurar que `llm_specialized_evaluation` siempre esté presente (ya lo está en la rama).
- **Impacto esperado:** habilita consumo limpio en assembler/UI.

### `backend/evaluacion/engine/communication_visual_evaluator.py`
- **Responsabilidad actual:** produce visual agregado + `llm_specialized_evaluation` desde visual synthesis (o vacío/fallback).
- **Problema actual:** UI no consume specialized visual directo.
- **Cambio propuesto:** sin rehacer evaluación; sólo normalizar fallback del specialized (si faltara) para contrato estable.
- **Impacto esperado:** robustez del render en modo degradado.

### `backend/evaluacion/engine/communication_synthesis.py`
- **Responsabilidad actual:** score global + resumen + recomendaciones.
- **Problema actual:** no técnico; el problema es de consumo UI.
- **Cambio propuesto:** sin cambios de lógica LLM.
- **Impacto esperado:** mantener foco “global-only”.

## 4.2 Contratos

### `backend/evaluacion/contracts/communication_models.py`
- **Responsabilidad actual:** define contrato report y entidades intermedias.
- **Problema actual:** `UiCommunicationReportV1` no expone secciones render-ready específicas para AIDA/audio/visual especializado.
- **Cambio propuesto:** añadir campos UI-oriented mínimos:
  - `content_aida_feedback` (4 bloques explícitos)
  - `audio_specialized_feedback`
  - `visual_specialized_feedback`
  - opcional `ui_sections_version` para versionado suave
- **Impacto esperado:** elimina heurísticas frontend y reduce acoplamiento implícito.

## 4.3 Assembler

### `backend/evaluacion/engine/communication_report_assembler.py`
- **Responsabilidad actual:** compone `UiCommunicationReportV1` desde outputs de rama + síntesis.
- **Problema actual:** no entrega sección AIDA render-ready ni módulos especializados independientes para entrega verbal.
- **Cambio propuesto:**
  1. Extraer `content_output.llm_specialized_evaluation` a `content_aida_feedback`.
  2. Extraer `delivery_output.llm_specialized_evaluation` a `audio_specialized_feedback`.
  3. Extraer `visual_output.llm_specialized_evaluation` a `visual_specialized_feedback`.
  4. Mantener `block_cards` sin romper API (compatibilidad).
- **Impacto esperado:** frontend renderiza directo, sin reconstrucciones.

## 4.4 Frontend

### `backend/comunicacion_app/report_view.js`
- **Responsabilidad actual:** render snapshot de feedback.
- **Problemas actuales:**
  - reconstruye AIDA desde `block_cards` por índice;
  - infiere entonación/gestos con keywords;
  - muestra metadata técnica en grabación;
  - resumen introduce subbloques no deseados.
- **Cambio propuesto:**
  1. Header: estrellas visuales sin texto numérico de estrellas.
  2. Renombrar sección a “Resumen” y mostrar sólo `summary_short_2_3_lines`.
  3. AIDA: render 4 tarjetas desde `content_aida_feedback` real.
  4. Entrega verbal: dos tarjetas blancas explícitas desde `audio_specialized_feedback` y `visual_specialized_feedback`.
  5. Grabación: eliminar `recording_id` y `video_ref` visibles.
  6. Recomendaciones: mantener 0..4 desde global.
- **Impacto esperado:** pantalla alineada a objetivo funcional sin tocar arquitectura.

## 4.5 Tests

### Archivos a ajustar/añadir
- `backend/tests/test_communication_report_contract.py`
- `backend/tests/test_communication_report_renderer.py`
- Nuevo test sugerido: `backend/tests/test_communication_report_ui_sections.py`

**Objetivo:** validar que el report trae secciones especializadas y que la UI ya no depende de reconstrucciones por índice/keywords.

---

## 5) Cambios exactos de responsabilidad (quién produce/transforma/renderiza)

## LLM de contenido
- **Produce:** `attention|interest|development|action` con `score_1_3,label,reason_short`.
- **No debe producir:** layout/UI details.

## LLM de audio
- **Produce:** `score_1_5,label,reason_short` de entonación/pausas.
- **No debe producir:** resumen global ni estructura de pantalla.

## LLM visual
- **Produce:** `score_1_5,label,reason_short` de gesticulación (tras síntesis visual).
- **No debe producir:** narrativa global.

## LLM final global
- **Produce:** `score_global_100`, `summary_short_2_3_lines`, `recommendations(0..4)`.
- **No debe producir:** reemplazo de AIDA ni specialized feedback.

## Assembler
- **Produce:** contrato UI explícito (secciones render-ready), mapeando 1:1 desde fuentes correctas.
- **No debe hacer:** reinterpretación heurística de textos para “adivinar” secciones.

## Frontend
- **Produce:** presentación visual (colores, chips, layout, estrellas derivadas).
- **No debe hacer:** deducciones semánticas por índices/keywords para reconstruir contenido.

---

## 6) Outputs que habría que ajustar (si aplica)

## 6.1 Outputs que ya sirven (no tocar)
- `CommunicationContentAidaEvalV1` (AIDA real).
- `CommunicationSpecializedDimensionEvalV1` para audio/visual.
- `CommunicationGlobalSynthesisLlmOutputV1` para global.

## 6.2 Ajustes pequeños recomendados
- Garantizar presencia de specialized feedback en fallback (`delivery`/`visual`) con shape estable para UI (aunque valor sea degradado).
- Añadir adaptadores en assembler para mapear specialized→UI contract explícito.

## 6.3 Outputs desaprovechados hoy
- `content_output.llm_specialized_evaluation` (AIDA completo).
- `delivery_output.llm_specialized_evaluation`.
- `visual_output.llm_specialized_evaluation`.

## 6.4 Outputs que hoy se aplanan/pierden
- granularidad AIDA (se aplana a `block_cards`).
- señal especializada audio/visual (se mezcla en summaries/details).

---

## 7) Reconstrucciones incorrectas a eliminar

1. **AIDA por índice** (`block_cards[0..3]` + títulos fijos).  
   → Reemplazar por `content_aida_feedback` directo.

2. **Entonación/Gesticulación por keyword matching** en bloques/recomendaciones.  
   → Reemplazar por `audio_specialized_feedback` y `visual_specialized_feedback`.

3. **Resumen derivado con subfrases inventadas** (“Lo más fuerte”, “Prioridad…”).  
   → Reemplazar por resumen global único.

4. **Exposición de metadata técnica** (`recording_id`, `video_ref`) en sección de video.  
   → Ocultar en UI final.

---

## 8) Propuesta de contrato final ideal para la pantalla (orientado a UI)

> Propuesta incremental, compatible: añadir campos nuevos sin romper los existentes.

```json
{
  "schema_version": "ui_communication_report.v2",
  "header": {
    "report_title": "Evaluación de tu comunicación oral",
    "score_global_100": 82,
    "stars_0_5": 4.1
  },
  "global_summary": {
    "text": "Has comunicado con claridad..."
  },
  "content_aida_feedback": {
    "attention": {"score_1_3": 3, "label": "correcto", "reason_short": "..."},
    "interest": {"score_1_3": 2, "label": "mejorable", "reason_short": "..."},
    "development": {"score_1_3": 3, "label": "correcto", "reason_short": "..."},
    "action": {"score_1_3": 2, "label": "mejorable", "reason_short": "..."}
  },
  "delivery_specialized_feedback": {
    "audio": {"score_1_5": 4, "label": "medio-alto", "reason_short": "..."},
    "visual": {"score_1_5": 3, "label": "medio", "reason_short": "..."}
  },
  "media": {
    "playback_url": "/api/.../video",
    "poster_frame_ref": "...",
    "mime_type": "video/webm"
  },
  "recommendations": {
    "items": [{"title": "...", "description": "..."}]
  },
  "compat": {
    "block_cards": ["..."],
    "global_synthesis": {"...": "..."}
  }
}
```

### Notas de diseño
- UI render principal usa `global_summary`, `content_aida_feedback`, `delivery_specialized_feedback`, `recommendations`, `media`.
- `compat.block_cards` mantiene backward compatibility transitoria.

---

## 9) Orden recomendado de implementación

## Fase 0 — Blindaje (sin cambios funcionales)
1. Añadir tests que documenten comportamiento deseado de UI objetivo.
2. Añadir snapshots/fixtures de report con specialized feedback.

## Fase 1 — Contrato y assembler (backend)
1. Extender modelos `UiCommunicationReport` con secciones nuevas.
2. Mapear specialized outputs en `assemble_communication_report`.
3. Mantener `block_cards` y campos actuales para compatibilidad.
4. Validar tests de contrato API.

## Fase 2 — Render frontend
1. Header: estrellas sin texto numérico adicional.
2. Resumen: título “Resumen” + párrafo único.
3. AIDA: 4 tarjetas desde `content_aida_feedback`.
4. Entrega verbal: dos tarjetas especializadas explícitas.
5. Grabación: ocultar metadata técnica.
6. Recomendaciones: mantener 0..4.

## Fase 3 — Limpieza controlada
1. Marcar rutas heurísticas viejas como deprecated.
2. Mantener fallback temporal bajo feature flag o guardas de compatibilidad.
3. Retirar heurísticas sólo cuando tests de integración pasen en CI y en entorno manual.

---

## 10) Riesgos y validaciones

## Riesgos
1. **Compatibilidad de clientes existentes** que consuman `block_cards`.
2. **Datos specialized faltantes** en escenarios fallback/placeholders.
3. **Regresiones visuales** al cambiar estructura de render.
4. **Inconsistencia semántica** entre labels/scores y color chips en UI.

## Validaciones técnicas recomendadas

### Contrato backend
- Test API `/report` con asserts de nuevos campos especializados.
- Test de fallback: specialized feedback presente aun en modo degradado.

### Frontend renderer
- Test unitario fuente de AIDA: verificar que no usa índices de `block_cards`.
- Test unitario de “entrega verbal” sin keyword matching.
- Test de ocultación de metadata técnica (sin `recording_id/video_ref` visibles).
- Test snapshot DOM para estructura final objetivo.

### Integración E2E
- Caso con todas las ramas reales (llm/mock): verificar secciones completas.
- Caso con audio placeholder y visual real.
- Caso con visual fallback y audio real.
- Caso con 0 recomendaciones.

### QA funcional manual
- Verificar que “Acción” siempre viene de AIDA real.
- Verificar color mapping AIDA: `correcto→verde`, `mejorable→amarillo`, `mal→rojo`.
- Verificar que resumen es único párrafo corto.
- Verificar que recomendaciones no se rellenan artificialmente.

---

## Criterio de aceptación del plan (Definition of Done para implementación futura)

Se considerará completado cuando:
1. La UI renderice cada sección desde su fuente correcta sin reconstrucciones heurísticas.
2. AIDA muestre 4 bloques reales (incluido Acción) con color + frase breve y sin score /100.
3. Entrega verbal se muestre en dos tarjetas separadas: audio y gesticulación.
4. Cabecera y resumen cumplan exactamente formato objetivo.
5. Grabación no muestre metadata técnica interna.
6. Recomendaciones provengan de síntesis global (0..4) sin relleno.
7. Tests de contrato/render/E2E queden en verde.

