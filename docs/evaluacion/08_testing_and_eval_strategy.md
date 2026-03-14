# 08 — Testing y estrategia de evals

## 0) Objetivo

Asegurar que el evaluador produce salidas útiles, consistentes y reproducibles sin contaminar el sistema conversacional existente.

## 1) Principio crítico de validación

Evaluar calidad sobre base principal de diálogo. Las pruebas deben detectar cualquier dependencia excesiva de trazas internas.

## 2) Matriz de pruebas

## A. Unit tests

1. `input_bundle_builder`
   - reconstrucción de turnos correcta,
   - stats coherentes,
   - `trace_digest` reducido/opcional.
2. `input_shaping`
   - mapping correcto bundle → subinput core/trajectory.
3. `reconciliation`
   - casos de contradicción core/trajectory.
4. `provenance`
   - hashes y freeze deterministas.

## B. Contract tests

- validación strict de 6 contratos:
  - bundle,
  - core runner input,
  - trajectory runner input,
  - core output,
  - trajectory output,
  - ui report.

## C. Integration tests

- create/status/report con repositorio in-memory,
- runners mock + validación real,
- fallos duros y correcciones seguras.

## D. Regression tests de no-ruptura

- mantener verdes tests existentes de `interfaz_usuario` y negociación.
- añadir smoke test específico:
  - turn endpoint funciona igual antes/después de incluir router feedback.

## 3) Estrategia eval-driven (datasets)

Carpeta nueva propuesta: `backend/evaluacion/evals/datasets`.

- `feedback_core_fixture_cases.jsonl`
- `feedback_trajectory_fixture_cases.jsonl`
- `feedback_reconciliation_cases.jsonl`
- `feedback_e2e_cases.jsonl`

Cada caso debe incluir:

- input snapshot,
- output candidato,
- expected checks estructurales,
- expected reconciliation behavior.

## 4) Calibración humana

- muestreo semanal de reportes reales,
- checklist por bloque + trayectoria,
- registro de discrepancias en `manual_review_log.jsonl`,
- acciones de ajuste: prompt, rubric, shaping o validación.

## 5) Métricas operativas mínimas

- `% schema valid` por runner,
- `% reconciliation hard-fail`,
- latencia p50/p95 total job,
- `% jobs completed`,
- `% reportes aprobados en revisión humana`.

## 6) Pruebas específicas anti-abuso de trazas

Agregar casos donde:

- `trace_digest` vacío,
- `trace_digest` conflictivo con diálogo,
- `trace_digest` presente pero irrelevante.

Resultado esperado: el evaluador mantiene juicio principal anclado en diálogo y no deriva por trazas.
