# Fase 4 — Síntesis global final + assembler/report compatible

## 1. Objetivo exacto de la fase

Implementar:

- cuarta LLM de síntesis global que combine contenido + delivery + visual,
- actualización del assembler para incorporar conclusiones globales,
- compatibilidad total con report/frontend/exports/final_result existentes.

Queda fuera:

- cambios de contrato del bridge Moodle,
- cambios de secuencia embed final_result.

## 2. Por qué esta fase va en este orden

La síntesis depende de outputs reales y estables de fases 1-3. Hacerla antes introduciría alta inestabilidad y duplicación de trabajo.

## 3. Archivos exactos a tocar

### Existentes a modificar

- `backend/evaluacion/engine/communication_report_assembler.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/contracts/communication_models.py`
- `backend/evaluacion/engine/communication_evaluators.py` (orquestación final)
- `backend/tests/test_communication_report_contract.py`
- `backend/tests/test_communication_report_exports_integrity.py`
- `backend/tests/test_communication_final_result_contract.py`

### Nuevos recomendados

- `backend/evaluacion/engine/communication_synthesis.py`
- `backend/evaluacion/prompts/communication_final_synthesis_prompt.txt`
- `backend/tests/test_communication_synthesis_contract.py`
- `backend/tests/test_communication_synthesis_consistency.py`

## 4. Cambios exactos por archivo

### `communication_report_assembler.py`
- Hoy: arma report con outputs simples y placeholders.
- Cambio: integrar salida de síntesis global (diagnóstico, fortalezas, prioridades, plan de mejora).
- Riesgo: romper shape de bloques/report.

### `communication_service.py`
- Cambio: insertar etapa `synthesis_ready` antes de `assembling_report`.
- Riesgo: retries y tiempos de espera al encadenar cuarta llamada LLM.

### `communication_models.py`
- Cambio: contratos de síntesis (`CommunicationGlobalSynthesisInput/Output`), manteniendo `UiCommunicationReportV1` compatible.
- Riesgo: mezclar campos técnicos con lenguaje usuario.

### Tests de report/final_result
- Cambio: ampliar cobertura de nuevos campos sin alterar contrato actual de exports/final_result.
- Riesgo: fragilidad de tests por textos de síntesis.

## 5. Funciones, clases o módulos a crear o modificar

- `build_global_synthesis_input(context, content_eval, delivery_eval, visual_eval) -> CommunicationGlobalSynthesisInputV1`
- `synthesize_global_communication_feedback(input: CommunicationGlobalSynthesisInputV1) -> CommunicationGlobalSynthesisOutputV1`
- `validate_synthesis_schema(raw_llm_output) -> CommunicationGlobalSynthesisOutputV1`
- `merge_synthesis_into_report(report, synthesis_output) -> UiCommunicationReportV1`
- `derive_global_score(content_eval, delivery_eval, visual_eval, synthesis_output) -> int`

## 6. Contratos de datos

### `CommunicationGlobalSynthesisInputV1`
- `evaluation_id`
- `context`
- `content_evaluation`
- `delivery_evaluation`
- `visual_evaluation`
- `evidence_summary`

### `CommunicationGlobalSynthesisOutputV1`
- `global_score_0_100`
- `global_diagnosis`
- `top_strengths[]`
- `priority_improvements[]`
- `action_plan[]`
- `friendly_summary`
- `consistency_notes[]`

Compatibilidad:

- nuevos campos del report deben ser aditivos.
- no eliminar campos existentes consumidos por frontend y final_result (`exports`, `media`, `video_panel`, etc.).

## 7. Stages del job afectados

Stages fase 4:

- `synthesis_started`
- `synthesis_ready`
- `assembling_report`
- `completed`

Dependencia:

- `synthesis_ready` requiere outputs exitosos de contenido + delivery + visual.

## 8. Testing

### Unitarios
- input builder de síntesis,
- validación de schema de síntesis,
- cálculo de score global determinista.

### Integración
- pipeline completo (fases 1-4) con providers mock.
- consistencia entre evidencias y resumen final.

### Regresión
- report API shape estable para frontend actual.
- exports (`summary_html`, `report_json`, png) intactos.
- `final_result` y bridge Moodle sin cambio contractual.

## 9. Riesgos de la fase

1. redundancia entre recomendaciones por evaluador y síntesis,
2. contradicciones entre subscores,
3. salida demasiado extensa o poco accionable.

Mitigación:

- prompt de síntesis con reglas de deduplicación y priorización,
- verificación de consistencia antes de ensamblar report,
- límites de longitud por campo de salida.

## 10. Criterio de aceptación

1. existe output de síntesis global estructurado y estable,
2. report final incluye narrativa global clara sin romper shape,
3. exports y final_result permanecen compatibles,
4. regresión del bridge embed/Moodle sigue en verde.

## 11. Qué NO entra en esta fase

- rediseño visual de frontend,
- cambios de contrato de final_result/ACK,
- nuevas features fuera del objetivo evaluativo multimodal.
