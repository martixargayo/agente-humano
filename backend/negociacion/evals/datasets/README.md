# Evals datasets

Este directorio separa explícitamente dos capas:

- `*_fixture_cases.jsonl`: casos deterministas para validar contratos y graders con `candidate_output`.
- `*_live_cases.jsonl`: casos para ejecutar nodos/pipeline reales y luego calificar outputs reales.
- `end_to_end_mock_cases.jsonl`: harness de integración E2E con mocks explícitos de nodos.

Los archivos legacy (`*_cases.jsonl`) se mantienen por compatibilidad y apuntan conceptualmente a la capa fixture/mock.
