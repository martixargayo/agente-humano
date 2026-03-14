# Subsistema de evaluación de desempeño (índice)

Esta carpeta se mantiene en `docs/` (raíz) y no en `backend/docs/` porque documenta una capacidad transversal (backend + frontend + UX + evals), no solo forensics internos del backend.

## Estado de decisiones

### Decisiones cerradas (NO reabrir en implementación v1)

- Evaluación del **desempeño del usuario** (no del agente).
- Pipeline de evaluación post-cierre, aditivo al flujo conversacional.
- Contratos principales:
  - `feedback_input_bundle_v1` (código)
  - `feedback_report_core_v1` (LLM)
  - `turn_trajectory_v1` (LLM)
  - `ui_feedback_report_v1` (ensamblador backend)
- Structured outputs estrictos (`strict: true`, required completos, `additionalProperties: false`).
- Jobs con estado + polling.
- Base analítica centrada en diálogo; trazas internas con uso mínimo/defensivo.
- Recomendación de modelo v1: `gpt-5.4` para core y trajectory.

### Preguntas abiertas (sí discutir)

- Durabilidad de persistencia más allá de in-memory en v1.1.
- SLAs exactos de latencia UX por entorno.
- Política de reintentos transitorios exacta (número final).

## Navegación recomendada

1. [00_overview.md](./00_overview.md)
2. [01_product_vision.md](./01_product_vision.md)
3. [02_architecture.md](./02_architecture.md)
4. [03_contracts.md](./03_contracts.md)
5. [04_orchestration_and_jobs.md](./04_orchestration_and_jobs.md)
6. [05_prompting_strategy.md](./05_prompting_strategy.md)
7. [06_repo_layout_and_file_plan.md](./06_repo_layout_and_file_plan.md)
8. [07_frontend_flow.md](./07_frontend_flow.md)
9. [08_testing_and_eval_strategy.md](./08_testing_and_eval_strategy.md)
10. [09_implementation_phases.md](./09_implementation_phases.md)
11. [10_open_questions.md](./10_open_questions.md)
12. [11_input_shaping_and_runner_inputs.md](./11_input_shaping_and_runner_inputs.md)
13. [12_repo_change_impact_plan.md](./12_repo_change_impact_plan.md)

## Rutas rápidas por rol

- Backend engine: `02` → `03` → `04` → `11` → `06`.
- Prompt/model runners: `05` → `03` → `11`.
- Frontend: `01` → `07` → contrato UI en `03`.
- QA/evals: `08` → `04` → `11` → `10`.
- Integración segura (no romper flujo actual): `12`.
