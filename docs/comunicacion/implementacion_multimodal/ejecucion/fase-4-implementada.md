# Fase 4 implementada — síntesis global final + integración en report

## 1. Objetivo real de la fase
Añadir una capa de síntesis global que combine contenido, delivery y visual para producir una conclusión final estructurada, trazable y compatible con el report actual y con final_result.

## 2. Decisión técnica tomada
Se implementó una síntesis **determinista/heurística encapsulada** en `communication_synthesis.py` (sin dependencia externa en tests):
- input tipado `CommunicationGlobalSynthesisInputV1`
- output tipado `CommunicationGlobalSynthesisOutputV1`
- cálculo reproducible de score global y conclusiones

## 3. Cómo funciona la síntesis global
Flujo:
1. Se construye input de síntesis desde salidas parciales (`content_output`, `delivery_output`, `visual_output`) y un `evidence_summary`.
2. Se calcula score global con combinación ponderada + ajuste por consistencia.
3. Se generan campos estructurados:
   - `global_score_0_100`
   - `global_diagnosis`
   - `top_strengths[]`
   - `priority_improvements[]`
   - `action_plan[]`
   - `friendly_summary`
   - `consistency_notes[]`
4. El assembler integra la síntesis en `UiCommunicationReportV1` como campo aditivo `global_synthesis`.

## 4. Cómo se resuelven contradicciones entre evaluadores
- Se calcula dispersión entre scores parciales (`max - min`).
- Si la dispersión supera umbrales, se añade penalización al score global y se registran `consistency_notes`.
- Si algún bloque está en modo placeholder, se agrega nota explícita de degradación.

## 5. Cómo se calcula el score global
- Base ponderada: `contenido 45% + delivery 35% + visual 20%`.
- Penalización de consistencia:
  - dispersión > 50 => `-10`
  - dispersión > 35 => `-5`
  - en otro caso => `0`
- Resultado final clamped en `[0, 100]`.

## 6. Archivos creados/modificados
### Creados
- `backend/evaluacion/engine/communication_synthesis.py`
- `backend/tests/test_communication_phase4_synthesis_and_report.py`

### Modificados
- `backend/evaluacion/contracts/communication_models.py`
- `backend/evaluacion/engine/communication_evaluators.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/engine/communication_report_assembler.py`
- `backend/comunicacion/storage/models.py`
- `backend/tests/test_communication_report_contract.py`
- `backend/tests/test_communication_report_exports_integrity.py`
- `backend/tests/test_communication_status_api.py`

## 7. Stages añadidos
- `synthesis_started`
- `synthesis_ready`

## 8. Tests ejecutados
- `python -m pytest backend/tests/test_communication_phase4_synthesis_and_report.py -q`
- `python -m pytest backend/tests/test_communication_report_contract.py -q`
- `python -m pytest backend/tests/test_communication_final_result_contract.py -q`
- `python -m pytest backend/tests/test_communication_report_exports_integrity.py -q`
- `python -m pytest backend/tests/test_communication_status_api.py -q`

## 9. Qué NO se ha tocado
- bridge/embed/Moodle
- contrato de `final_result`
- frontend (`backend/comunicacion_app/*`)
- rediseño de HTML/CSS del report

## 10. Veredicto de compatibilidad
Se mantiene compatibilidad hacia atrás:
- `UiCommunicationReportV1` sigue estable y solo recibe un campo aditivo (`global_synthesis`).
- `summary_html`, `report_json`, `snapshot_png_dataurl` permanecen operativos.
- `final_result` conserva contrato y pruebas de integridad.
