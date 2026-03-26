# Matriz de validación E2E · Comunicación (Fases 1-2-3)

Fecha: 2026-03-26 (UTC)

## Cobertura y método
- **Automático backend/API**: `pytest` + flujo E2E con `fastapi.testclient`.
- **Contrato UI estático**: checks de markup/JS/CSS por presencia/ausencia de elementos críticos.
- **Manual asistido pendiente**: hardware/navegador real (cámara/mic/permisos).

## Casos

| ID | Caso | Esperado | Método | Resultado | Evidencia |
|---|---|---|---|---|---|
| E2E-01 | Bootstrap sesión comunicación | 200 + contexto/activity/policy | TestClient API | ✅ PASS | `artifacts/e2e_api_results.json` (`flow.bootstrap`) |
| E2E-02 | Crear attempt | 200 + `status=draft` | TestClient API | ✅ PASS | `artifacts/e2e_api_results.json` (`flow.create_attempt`) |
| E2E-03 | Upload recording | 200 + `recording_id` + `playback_url` | TestClient API multipart | ✅ PASS | `artifacts/e2e_api_results.json` (`flow.upload_recording`) |
| E2E-04 | Submit evaluación | 200 + `evaluation_id` | TestClient API | ✅ PASS | `artifacts/e2e_api_results.json` (`flow.submit`) |
| E2E-05 | Poll status hasta completado | llega a `completed/report_available=true` | TestClient API | ✅ PASS | `artifacts/e2e_api_results.json` (`flow.poll_until_completed`) |
| E2E-06 | Fetch report final | 200 + payload esperado | TestClient API | ✅ PASS | `artifacts/e2e_api_results.json` (`flow.report_fetch`) |
| CONC-01 | Ownership status/report | otra sesión no puede leer evaluación ajena | TestClient API con otro `user/session` | ✅ PASS (404) | `artifacts/e2e_api_results.json` (`concurrency.ownership_*`) |
| CONC-02 | Doble submit mismo attempt | no crea evaluación nueva (idempotencia básica) | TestClient API submit x2 | ✅ PASS | `artifacts/e2e_api_results.json` (`concurrency.double_submit.same_eval=true`) |
| CONC-03 | Dos sesiones en paralelo | sesiones separadas sin contaminación | 2 threads TestClient | ✅ PASS | `artifacts/e2e_api_results.json` (`concurrency.parallel_sessions`) |
| UX-01 | No regresión de CTAs técnicos legacy | no reaparece preview/register/submit legacy | check estático | ✅ PASS | `artifacts/ui_contract_checks.json` |
| UX-02 | Fase 2 recording UI presente | AIDA visible, self-view, panel AV, badges, waveform | check estático | ✅ PASS | `artifacts/ui_contract_checks.json` |
| UX-03 | Loading parity presente | loading layout/shimmer/floating/stage pill | check estático | ✅ PASS | `artifacts/ui_contract_checks.json` |
| UX-04 | Processing sin datos técnicos al usuario | no `evaluation_id/status/stage` visibles en copy | check estático | ✅ PASS | `artifacts/ui_contract_checks.json` |
| UX-05 | Report Fase 3 presente | hero/resumen/AIDA/entonación/gestos | check estático | ✅ PASS | `artifacts/ui_contract_checks.json` |

## Comandos ejecutados (resumen)
- `PYTHONPATH=/workspace/agente-humano pytest -q backend/tests/test_comunicacion_attempt_api.py backend/tests/test_comunicacion_bootstrap_api.py backend/tests/test_communication_status_api.py backend/tests/test_communication_report_api.py backend/tests/test_communication_report_export_contract.py backend/tests/test_communication_report_exports_integrity.py backend/tests/test_communication_audit_pipeline_e2e.py backend/tests/test_communication_evaluation_job.py backend/tests/test_comunicacion_embed_final_result_contract.py`
- `PYTHONPATH=/workspace/agente-humano pytest -q backend/tests/test_communication_status_api.py backend/tests/test_comunicacion_attempt_api.py backend/tests/test_comunicacion_recording_repository.py backend/tests/test_communication_evaluation_job.py`
- Script E2E API + concurrencia básica (artefacto JSON).
- Script de contrato UI estático (artefacto JSON).
