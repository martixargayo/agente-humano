# 04 - Matriz de validación y regresión final (comunicación)

Fecha de ejecución: 2026-03-26

## Alcance
Esta matriz valida regresión funcional y de contrato del flujo completo de `comunicacion` después de los cambios recientes en frontend y hardening de entrega final.

## Matriz

| ID | Caso | Esperado | Método | Resultado | Evidencia |
|---|---|---|---|---|---|
| API-01 | Bootstrap de sesión | `POST /api/comunicacion/sessions/bootstrap` responde 200 y devuelve contexto/sesión | `pytest backend/tests/test_comunicacion_bootstrap_api.py` | ✅ PASS | `docs/comunicacion/validacion/artifacts/pytest_regresion_comunicacion_2026-03-26.txt` |
| API-02 | Create attempt + lectura attempt | attempt creado y leíble por owner | `pytest backend/tests/test_comunicacion_attempt_api.py` | ✅ PASS | `docs/comunicacion/validacion/artifacts/pytest_regresion_comunicacion_2026-03-26.txt` |
| API-03 | Upload recording | upload JSON/multipart registra recording y playback URL | `pytest backend/tests/test_comunicacion_attempt_api.py` | ✅ PASS | idem API-01 |
| API-04 | Submit + polling/status | submit produce `evaluation_id`, estado consultable y ownership aplicado | `pytest backend/tests/test_communication_status_api.py` | ✅ PASS | idem API-01 |
| API-05 | Fetch report final | endpoint report responde contrato esperado | `pytest backend/tests/test_communication_report_api.py` | ✅ PASS | idem API-01 |
| API-06 | Contrato de report | payload de report conserva estructura esperada | `pytest backend/tests/test_communication_report_contract.py` | ✅ PASS | idem API-01 |
| API-07 | Contrato export interno (JSON/HTML/PNG) | hooks y funciones de export siguen disponibles | `pytest backend/tests/test_communication_report_export_contract.py` | ✅ PASS | idem API-01 |
| API-08 | Integridad de exportes | exports del report siguen coherentes con render/captura | `pytest backend/tests/test_communication_report_exports_integrity.py` | ✅ PASS | idem API-01 |
| API-09 | Contrato final_result | envelope/payload `final_result` válido | `pytest backend/tests/test_communication_final_result_contract.py` | ✅ PASS | idem API-01 |
| API-10 | Contrato embed ACK | ACK `final_result_saved` valida y flujo embed no se rompe | `pytest backend/tests/test_comunicacion_embed_final_result_contract.py` | ✅ PASS | idem API-01 |
| API-11 | Pipeline de evaluación | evaluación completa de comunicación cierra de punta a punta | `pytest backend/tests/test_communication_evaluation_job.py` + `test_communication_audit_pipeline_e2e.py` | ✅ PASS | idem API-01 |
| API-12 | Concurrencia básica | comportamiento en paralelo y aislamiento básico de sesiones/attempts | `pytest backend/tests/test_communication_parallel_pipeline.py` | ✅ PASS | idem API-01 |
| REG-01 | Estructura pública `index/app/report/styles` | assets sirven y contienen estructura vigente (setup, loading/report/error desacoplados) | `pytest backend/tests/test_public_comunicacion_app_assets.py` + `test_public_comunicacion_serving.py` | ✅ PASS | idem API-01 |
| REG-02 | No regresión visual/estructural crítica | no reaparece `screenProcessing`; `screenUploading` no visible; autoentrega conectada | check estructural por script | ✅ PASS | `docs/comunicacion/validacion/artifacts/ui_regression_contract_checks_2026-03-26.json` |
| REG-03 | Repositorio y ownership base | repositorios de attempts/recordings no rompen invariantes | `pytest backend/tests/test_comunicacion_attempt_repository.py backend/tests/test_comunicacion_recording_repository.py` | ✅ PASS | `docs/comunicacion/validacion/artifacts/pytest_repositorio_comunicacion_2026-03-26.txt` |

## Cobertura frente a objetivos solicitados
- Flujo principal `bootstrap -> attempt -> upload -> submit -> poll -> report`: cubierto (API-01..05, API-11).
- Regresión UX por etapas (setup/AIDA/recording/review/loading/report): cubierto por tests públicos y checks estructurales (REG-01, REG-02).
- `final_result` / embed / autoentrega: cubierto por contratos y harness JS/Pydantic (API-09, API-10).
- Export interno sin botones visibles: cubierto por contrato de funciones/harness (API-07, API-08).
- Concurrencia/ownership/doble submit: cubierto por batería de attempt/status/paralelo + repositorio (API-02, API-04, API-12, REG-03).
