# Plan de implementación por fases: evaluación visual multimodal por frames (OpenAI)

Fecha: 2026-03-27  
Estado: **Plan previo a implementación** (sin cambios funcionales)

---

# 1. Resumen ejecutivo

## Número de fases propuesto: **3 fases**
Propongo 3 fases (no 2) por control de riesgo:

- **Fase 1 — Fundaciones internas + contratos + selección de frames + tests base**
  - Salida: el sistema sigue funcionando igual (`metadata`), pero ya existe infraestructura interna validada para sampling uniforme (<=90) y batching (30 con regla `<6`).
- **Fase 2 — Rama OpenAI batch-by-batch (shadow/opt-in) + persistencia parcial + resiliencia**
  - Salida: evaluación visual LLM funcional detrás de flag `llm_v1`, con fallback automático a metadata, sin cambiar default.
- **Fase 3 — Síntesis final + integración de reporte + rollout controlado + no-regresión**
  - Salida: rama `llm_v1` integrada end-to-end y con plan de activación gradual.

## Orden recomendado
1) Fase 1 (contratos y determinismo).  
2) Fase 2 (dependencia externa y errores).  
3) Fase 3 (acople final UX/report + rollout).

## Criterio de salida por fase
- **F1 done:** tests de sampling/batching y compatibilidad en verde; sin cambios de comportamiento por defecto.
- **F2 done:** pipeline `llm_v1` produce batch outputs persistibles con retries/fallback y sin romper `metadata`.
- **F3 done:** síntesis final estable + reportes + e2e + no-regresión aprobada.

---

# 2. Mapa de impacto del sistema actual

## Flujo visual actual end-to-end (real)
1. **Construcción de bundle**: `build_communication_feedback_input_bundle(...)` obtiene transcript/audio/visual y arma `CommunicationFeedbackInputBundleV1`.  
2. **Extracción visual**: `extract_video_frames(...)` genera JPG temporales `frame_%03d.jpg`, arma `frame_manifest` con `frame_ref=file://...`, `timestamp_ms`, `quality`, `windows`.  
3. **Evaluación visual actual**: `evaluate_visual_from_features(...)` usa heurísticas de cobertura/calidad, no LLM multimodal.  
4. **Orquestación job**: `_run_communication_evaluation_job(...)` persiste artefactos, ejecuta ramas paralelas (`contenido`, `delivery`, `visual`) y arma reporte.

## Puntos exactos de intervención
- `backend/evaluacion/contracts/communication_models.py` (nuevos contratos batch/final).  
- `backend/evaluacion/engine/communication_frame_extractor.py` (opciones de extracción 1fps y metadatos de selección).  
- `backend/evaluacion/engine/communication_visual_evaluator.py` (nueva rama `llm_v1` + interfaz estable).  
- `backend/evaluacion/engine/communication_evaluators.py` (inyectar modo visual sin romper shape actual).  
- `backend/evaluacion/engine/communication_service.py` (persistencia de batch outputs y síntesis final LLM).  
- nuevos módulos engine para selector, cliente OpenAI y síntesis.

## Puntos que deben permanecer intactos
- Flujo actual `metadata` (default).  
- Contrato de salida principal que consume `communication_report_assembler.py` (`block_id/title/status_visual/score/details/subscores/recommendations/evidence_frames`).  
- API pública `/comunicacion/evaluations/{id}` y `/report`.

## Dependencias sensibles
- `openai` SDK ya existe en repo, pero la rama comunicación visual hoy no depende de OpenAI multimodal.  
- Persistencia de artefactos usa `DerivedArtifactRecord.kind` con conjunto literal actualmente cerrado.

## Riesgos de regresión
- Cambiar shape de `visual_output` puede romper report assembler.  
- Añadir nuevos `kind` sin actualizar contratos/storage puede romper auditoría o listados.  
- Timeouts en rama visual pueden degradar pipeline completo si fallback no está aislado.

---

# 3. Fase 1

## 3.1 Objetivo
Construir base determinista y testeable para:
- selección uniforme 1fps con cap 90,
- batching 30 + regla resto `<6`,
- contratos internos nuevos,
sin tocar comportamiento visual de producción por defecto.

## 3.2 Archivos a crear
1. `backend/evaluacion/engine/communication_visual_sampling.py`
   - utilidades puras (sin red):
     - `build_candidate_timestamps_1fps(duration_ms: int) -> list[int]`
     - `select_uniform_indices(total_candidates: int, max_frames: int = 90) -> list[int]`
     - `select_uniform_frames(candidates: list[CommunicationFrameSample], max_frames: int = 90) -> list[CommunicationFrameSample]`
     - `partition_frame_batches(frames: list[CommunicationFrameSample], target_batch_size: int = 30, min_tail_batch: int = 6) -> list[list[CommunicationFrameSample]]`
2. `backend/tests/test_communication_visual_sampling_plan.py`
3. `backend/tests/test_communication_visual_batching_plan.py`
4. `backend/tests/test_communication_visual_contracts_v1.py`

## 3.3 Archivos a modificar
1. `backend/evaluacion/contracts/communication_models.py`
2. `backend/evaluacion/contracts/__init__.py`
3. `backend/comunicacion/storage/models.py` (si se agregan kinds nuevos desde fase 1; opcional diferir a F2)
4. `backend/tests/test_communication_phase3_frames_and_visual.py` (solo si hay colisión de tipos/contract imports)

## 3.4 Cambios exactos por archivo

### A) `communication_models.py`
Añadir **nuevos modelos pydantic** (sin reemplazar los existentes):

- `CommunicationVisualSamplingStrategyV1`
  - `mode: Literal['uniform_1fps_capped_90']`
  - `candidate_fps: Literal[1] = 1`
  - `max_frames: int = 90`
  - `selection: Literal['uniform_full_duration']`
  - `batch_target: int = 30`
  - `tail_merge_threshold: int = 6`

- `CommunicationVisualBatchFrameRefV1`
  - `frame_id: str`
  - `timestamp_ms: int`
  - `frame_ref: str` (interno)
  - `detail: Literal['low'] = 'low'`

- `CommunicationVisualBatchEvalInputV1`
  - `evaluation_id`, `recording_id`, `batch_index`, `total_batches`, `video_duration_ms`
  - `sampling_strategy: CommunicationVisualSamplingStrategyV1`
  - `frames: list[CommunicationVisualBatchFrameRefV1]`
  - `rubric: dict[str, str]`

- `CommunicationVisualBatchEvalV1`
  - `schema_version`
  - `batch_score_1_5: int`
  - `evidence_sufficiency: Literal['low','medium','high']`
  - `hand_use_assessment`, `facial_expression_assessment`, `posture_assessment`
  - `strengths`, `weaknesses`, `limitations`, `cited_frame_ids`
  - `confidence: float`

- `CommunicationVisualFinalEvalV1`
  - `schema_version`
  - `global_score_1_5`, `label`, `diagnosis`, `temporal_consistency`
  - `top_strengths`, `top_weaknesses`, `recommendations`
  - `evidence_frame_ids`, `confidence`, `limitations`
  - `batch_summaries: list[CommunicationVisualBatchEvalV1]`

- `CommunicationVisualMode`
  - `Literal['metadata', 'llm_v1']`

**No tocar** modelos existentes (`CommunicationVisualEvaluationV1`, `CommunicationFrameManifestV1`) salvo añadir campos opcionales compatibles si realmente se necesitan.

### B) `contracts/__init__.py`
Exportar los nuevos modelos para evitar imports directos desde archivo interno.

### C) `communication_visual_sampling.py`
Implementar lógica pura:

1. `build_candidate_timestamps_1fps(duration_ms)`
   - regla: `N = max(1, floor(duration_ms/1000))`
   - timestamps `[i*1000 for i in range(N)]`

2. `select_uniform_indices(total_candidates, max_frames=90)`
   - if `N <= max_frames`: `[0..N-1]`
   - else center-bin:
     - `idx_j = floor((j + 0.5) * N / K)` para `j in 0..K-1`
   - deduplicación defensiva + relleno vecinos

3. `select_uniform_frames(candidates, max_frames=90)`
   - aplicar indices ordenados

4. `partition_frame_batches(frames, target_batch_size=30, min_tail_batch=6)`
   - chunks de 30
   - si último `<6` y hay chunk previo, merge con anterior

**No llamar OpenAI aquí.** Debe ser 100% determinista y unit-testable.

### D) Tests nuevos
- `test_communication_visual_sampling_plan.py`
  - 65s -> 65 candidatos
  - 90s -> 90
  - 91s -> 90 seleccionados uniformes (incluye cola)
  - 180s -> 90 seleccionados sobre toda duración (no solo primeros 90)
  - edge `<1s` -> 1 frame
- `test_communication_visual_batching_plan.py`
  - casos 65/66/89/90 exactos
- `test_communication_visual_contracts_v1.py`
  - validación strict de schemas y rangos

## 3.5 Configuración / flags
En esta fase, solo definir constantes (sin activar flujo):
- `COMM_VISUAL_MODE_DEFAULT='metadata'`
- `COMM_VISUAL_MAX_FRAMES=90`
- `COMM_VISUAL_BATCH_TARGET=30`
- `COMM_VISUAL_TAIL_MIN=6`
- `COMM_VISUAL_DETAIL='low'`

Pueden vivir en nuevo módulo:
- `backend/evaluacion/engine/communication_visual_config.py`

## 3.6 Tests
- Unitarios puros de selección y batching.
- Contratos pydantic.
- No e2e aún.

## 3.7 Riesgos
- Off-by-one en sampling uniforme.
- Duplicados por rounding.
- Casos borde en duración muy corta.

## 3.8 Criterios de validación / done
- Todos los tests nuevos en verde.
- Ningún test actual de comunicación roto.
- Sin cambios de comportamiento visible del modo metadata.

---

# 4. Fase 2

## 4.1 Objetivo
Activar rama `llm_v1` por lote con OpenAI Responses API, persistencia parcial y fallback robusto, sin cambiar default global.

## 4.2 Archivos a crear
1. `backend/evaluacion/engine/communication_visual_openai_client.py`
2. `backend/evaluacion/engine/communication_visual_batch_runner.py`
3. `backend/evaluacion/prompts/communication_visual_batch_evaluator_prompt.txt`
4. `backend/tests/test_communication_visual_openai_client.py`
5. `backend/tests/test_communication_visual_batch_runner.py`

## 4.3 Archivos a modificar
1. `backend/evaluacion/engine/communication_visual_evaluator.py`
2. `backend/evaluacion/engine/communication_evaluators.py`
3. `backend/evaluacion/engine/communication_service.py`
4. `backend/comunicacion/storage/models.py`
5. `backend/evaluacion/engine/communication_frame_extractor.py` (mínimo: helper para 1fps candidates reusables)
6. `backend/evaluacion/engine/communication_bundle_builder.py` (adjuntar metadatos si hace falta)

## 4.4 Cambios exactos por archivo

### A) `communication_visual_openai_client.py`
Funciones:
- `_build_client() -> openai.OpenAI | None`
- `build_responses_input_for_batch(batch_input: CommunicationVisualBatchEvalInputV1, prompt: str) -> list[dict]`
- `run_openai_visual_batch(...) -> CommunicationVisualBatchEvalV1`

Decisión de transporte de imágenes en F2:
- **baseline: data URL base64** desde `frame_ref=file://...`
- Motivo: evita capa externa de storage URL/file_id en primera entrega; acota dependencias.

Errores/retries/timeouts:
- retry exponencial corto (2 intentos extra) en errores transitorios.
- timeout por request configurable.
- mapear errores a excepción de dominio controlada (`CommunicationVisualLlmError`).

### B) `communication_visual_batch_runner.py`
Funciones:
- `build_batch_eval_inputs_from_manifest(...) -> list[CommunicationVisualBatchEvalInputV1]`
  - usa utilidades de F1
- `evaluate_visual_batches_openai(...) -> list[CommunicationVisualBatchEvalV1]`
  - ejecuta secuencial o paralelo acotado (recomendado secuencial en V1 para simplicidad)

### C) `communication_visual_evaluator.py`
Mantener API pública estable y agregar modo:
- función actual `evaluate_visual_from_features(...)` se mantiene para metadata.
- añadir:
  - `evaluate_visual_llm_v1_from_features(...)`
  - `evaluate_visual_with_mode(visual_features, recording_meta, mode='metadata'|'llm_v1')`

**Interfaz estable de salida**:
- devolver `CommunicationVisualEvaluationV1` para no romper ensamblador/report.
- mapear resultado LLM batch/final al shape actual (score/subscores/observations/recommendations/evidence_frames).

### D) `communication_evaluators.py`
En `evaluate_communication_visual(bundle)`:
- leer modo (`metadata` default).
- si `llm_v1`, usar rama nueva.
- si error o timeout -> fallback metadata con nota explícita en `details`.

### E) `communication_service.py`
En `_run_communication_evaluation_job(...)`:
- después de `frames_ready`, mantener pipeline paralelo existente.
- persistir artefactos nuevos:
  - `visual_batch_eval` (uno por lote)
  - `visual_llm_summary` (pre-síntesis)

Agregar funciones:
- `persist_visual_batch_eval_artifact(...)`
- `persist_visual_llm_summary_artifact(...)`

### F) `comunicacion/storage/models.py`
Extender `ArtifactKind`:
- agregar `visual_batch_eval`
- agregar `visual_llm_summary`
- (fase 3 agregará `visual_llm_final`)

### G) `communication_frame_extractor.py`
Sin romper firmas actuales:
- agregar opcional `sample_every_ms=1000` path utilizable desde batch runner.
- si ya existe suficiente, no forzar refactor grande.

## 4.5 Configuración / flags
Nuevo módulo config (si no se creó en F1):
- `COMM_VISUAL_MODE` (`metadata` por defecto)
- `COMM_VISUAL_OPENAI_MODEL` (`gpt-4.1-mini` default)
- `COMM_VISUAL_OPENAI_TIMEOUT_S`
- `COMM_VISUAL_OPENAI_MAX_RETRIES`
- `COMM_VISUAL_OPENAI_ENABLED` (kill-switch)

## 4.6 Tests
- `test_communication_visual_openai_client.py`
  - mock `openai.OpenAI().responses.create`
  - valida armado de input multimodal con `detail='low'`
  - valida parseo de structured output
- `test_communication_visual_batch_runner.py`
  - genera batches correctos
  - maneja fallos parciales
- `test_communication_visual_fallback_mode.py`
  - error OpenAI => fallback metadata sin romper salida

## 4.7 Riesgos
- Parseo de schema fallido por respuesta no estricta.
- Payload grande por base64.
- Latencia elevada por lote.

## 4.8 Criterios de validación / done
- Con `COMM_VISUAL_MODE=metadata`, salida idéntica a hoy.
- Con `llm_v1`, se obtiene evaluación visual válida (aunque sea básica) + artefactos parciales.
- Ante error OpenAI, pipeline completa con fallback y status coherente.

---

# 5. Fase 3

## 5.1 Objetivo
Completar síntesis final de lotes, integrar reportes de forma limpia, cerrar no-regresión y preparar rollout gradual.

## 5.2 Archivos a crear
1. `backend/evaluacion/engine/communication_visual_synthesis_llm.py`
2. `backend/evaluacion/prompts/communication_visual_synthesis_prompt.txt`
3. `backend/tests/test_communication_visual_synthesis_llm.py`
4. `backend/tests/test_communication_visual_mode_regression.py`
5. `backend/tests/test_communication_visual_pipeline_e2e_llm_mock.py`

## 5.3 Archivos a modificar
1. `backend/evaluacion/engine/communication_visual_evaluator.py`
2. `backend/evaluacion/engine/communication_service.py`
3. `backend/evaluacion/engine/communication_report_assembler.py`
4. `backend/comunicacion/storage/models.py`
5. `backend/tests/test_communication_evaluation_job.py`
6. `backend/tests/test_communication_parallel_pipeline.py`

## 5.4 Cambios exactos por archivo

### A) `communication_visual_synthesis_llm.py`
- `build_visual_synthesis_input(batch_outputs, manifest_meta, strategy) -> dict`
- `run_visual_synthesis_openai(...) -> CommunicationVisualFinalEvalV1`

### B) `communication_visual_evaluator.py`
- ruta `llm_v1` final:
  1. batch runner
  2. síntesis final
  3. mapeo a `CommunicationVisualEvaluationV1`
- subscores sugeridos mapeados a contrato actual:
  - `hand_use`, `expressivity`, `posture`, `coverage`

### C) `communication_service.py`
- persistir `visual_llm_final` artefacto nuevo.
- meter telemetría en stages (sin romper enumeración actual; agregar nuevos stages opcionales):
  - `visual_batch_analysis_started/ready`
  - `visual_synthesis_started/ready`

### D) `communication_report_assembler.py`
- no cambiar contrato de bloque visual base.
- opcional: incluir en `placeholders`/provenance una nota de `visual_mode` y `sampling_strategy`.

### E) `comunicacion/storage/models.py`
- agregar `visual_llm_final` a `ArtifactKind`.

## 5.5 Configuración / flags
- rollout progresivo:
  - `COMM_VISUAL_MODE=metadata` (default)
  - entornos internos: `llm_v1`
- kill-switch global: `COMM_VISUAL_OPENAI_ENABLED=false` fuerza metadata.

## 5.6 Tests
- síntesis final valida schema y agregación.
- e2e job con OpenAI mock para modo `llm_v1`.
- no-regresión modo `metadata`.
- pruebas de stage transitions y report assembly.

## 5.7 Riesgos
- Acople excesivo de nuevos campos al reporte.
- Inconsistencia entre batch outputs y síntesis final.

## 5.8 Criterios de validación / done
- E2E `llm_v1` estable con mock.
- E2E `metadata` intacto.
- Reportes exportables sin cambios incompatibles.

---

# 6. Contratos definitivos propuestos

## 6.1 Input por lote OpenAI
`CommunicationVisualBatchEvalInputV1`
- `evaluation_id: str`
- `recording_id: str`
- `batch_index: int`
- `total_batches: int`
- `video_duration_ms: int`
- `sampling_strategy: CommunicationVisualSamplingStrategyV1`
- `frames: list[CommunicationVisualBatchFrameRefV1]`
- `rubric: dict[str, str]`

## 6.2 Output parcial por lote
`CommunicationVisualBatchEvalV1`
- `batch_score_1_5: int`
- `evidence_sufficiency: low|medium|high`
- `hand_use_assessment: str`
- `facial_expression_assessment: str`
- `posture_assessment: str`
- `strengths: list[str]`
- `weaknesses: list[str]`
- `limitations: list[str]`
- `cited_frame_ids: list[str]`
- `confidence: float`

## 6.3 Output final síntesis
`CommunicationVisualFinalEvalV1`
- `global_score_1_5: int`
- `label: str`
- `diagnosis: str`
- `temporal_consistency: low|medium|high`
- `top_strengths: list[str]`
- `top_weaknesses: list[str]`
- `recommendations: list[str]`
- `evidence_frame_ids: list[str]`
- `confidence: float`
- `limitations: list[str]`
- `batch_summaries: list[CommunicationVisualBatchEvalV1]`

## 6.4 Tipos internos de persistencia
Nuevos artifact kinds:
- `visual_batch_eval`
- `visual_llm_summary`
- `visual_llm_final`

---

# 7. Plan de prompts

## Ubicación
- `backend/evaluacion/prompts/communication_visual_batch_evaluator_prompt.txt`
- `backend/evaluacion/prompts/communication_visual_synthesis_prompt.txt`

## Carga
Reusar patrón existente (`load_prompt_text(Path(...))` de runners/common o helper análogo).

## Separación
- prompt batch: análisis frame-level limitado a evidencia visible.
- prompt síntesis: agregación cross-batch sin sobreinferir continuidad.

## Validación structured output
- Usar Responses API con `text.format.type=json_schema` y `strict=true`.
- Parsear a modelos pydantic (`CommunicationVisualBatchEvalV1`, `CommunicationVisualFinalEvalV1`).
- si falla validación: retry corto; si persiste, fallback metadata.

---

# 8. Plan de integración con OpenAI

## Cliente
- `openai.OpenAI()` (mismo SDK ya usado en repo).

## Transporte de imágenes
### V1 recomendada: **base64 data URL**
- Pros: no requiere storage externo ni URL firmada.
- Contras: payload más grande.

### Evolución posterior (no V1)
- `file_id` vía Files API para reducir payload y reutilizar assets.

## `detail="low"`
- Setear por cada `input_image`.
- Registrar en artifact meta para auditoría.

## Retries / errores / timeouts
- timeout request configurable.
- retries limitados (2)
- clasificación de errores:
  - transient -> retry
  - schema/validation -> fallback
  - auth/config -> fallback inmediato + log estructurado

## Aislamiento de dependencia
- todo OpenAI en módulo `communication_visual_openai_client.py`.
- dominio evaluador consume interfaz abstracta (función runner), no SDK directo en múltiples archivos.

---

# 9. Plan de backward compatibility

## Convivencia `metadata` vs `llm_v1`
- `metadata` permanece intacto y por defecto.
- `llm_v1` opt-in por env/config.

## Selección de modo
Prioridad:
1. env `COMM_VISUAL_MODE`
2. default hardcoded `metadata`

## Fallback automático
- cualquier error en `llm_v1` => ejecutar `metadata` en el mismo job y continuar.
- agregar marca en `details` indicando fallback.

## Paths viejos que no deben romperse
- `evaluate_communication_visual(bundle)` debe seguir devolviendo el mismo shape.
- `assemble_communication_report(...)` no requiere cambios incompatibles.
- APIs de estado/reporte deben mantener contratos actuales.

---

# 10. Plan de testing

## 10.1 Unitarios (lógica pura)
- sampling uniforme:
  - no sesgo inicial
  - cobertura full-duration
  - edge cases de duración
- batching:
  - resto `<6` merge
  - resto `>=6` lote extra

## 10.2 Contracts/schema
- pydantic validate success/failure para input/output batch/final.

## 10.3 Cliente OpenAI mockeado
- construcción de payload con `input_image` + `detail=low`.
- parse de structured output.
- retries en errores transitorios.

## 10.4 Síntesis
- agregación coherente de parciales.
- confidence acotada por evidencia.

## 10.5 Integración de flujo
- job completo en `llm_v1` con mocks:
  - stages
  - persistencia artefactos nuevos
  - reporte final válido

## 10.6 Fallback
- simular fallo OpenAI y verificar salida metadata + job completed.

## 10.7 No-regresión modo actual
- ejecutar suite de comunicación existente (especialmente phase3/parallel/report/status).

---

# 11. Riesgos técnicos y mitigaciones

## Fase 1
- Riesgo: algoritmo erróneo de uniformidad.
- Mitigación: tests de distribución y edge cases.

## Fase 2
- Riesgo: inestabilidad proveedor externo.
- Mitigación: retries + timeout + fallback metadata + aislamiento módulo.

## Fase 3
- Riesgo: ruptura de contratos en reporte.
- Mitigación: mantener shape legacy y mapear internamente nuevos scores.

Riesgo transversal principal:
- deriva semántica entre lotes y síntesis.
- mitigación: esquema explícito + reglas de síntesis + tests deterministas con fixtures.

---

# 12. Orden exacto de implementación recomendado

1. Añadir contratos pydantic nuevos (sin conectar flujo).
2. Añadir módulo de sampling/batching + tests unitarios.
3. Añadir config/flags y defaults (metadata por defecto).
4. Añadir cliente OpenAI aislado + tests mock.
5. Añadir batch runner + tests.
6. Integrar `llm_v1` en visual evaluator con fallback interno.
7. Integrar persistencia artefactos nuevos en service.
8. Añadir síntesis final LLM + tests.
9. Ajustar report/provenance sólo de forma aditiva.
10. Ejecutar no-regresión completa.
11. Activar shadow mode.
12. Documentar métricas de rollout y criterios de promoción.

---

# 13. Preguntas abiertas o decisiones a cerrar antes de implementar

1. **Transporte V1** confirmado: ¿base64 obligatorio o aceptar `file_id` si está disponible?  
2. **Concurrencia de lotes**: ¿secuencial (más estable) o paralelo limitado (menor latencia)?  
3. **Modelo exacto default**: `gpt-4.1-mini` (recomendado) confirmado para entorno.  
4. **Política de artefactos**: ¿persistir payload de request redacted o sólo referencias + hashes?  
5. **SLO de latencia p95** objetivo para aprobar F3.

---

## Notas de alcance
- Este documento es exclusivamente de planificación previa.
- No propone activar comportamiento por defecto en esta etapa.
- Implementación condicionada a aprobación de fases.
