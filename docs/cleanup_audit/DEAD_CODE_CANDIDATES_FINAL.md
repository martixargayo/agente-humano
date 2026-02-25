# DEAD CODE CANDIDATES FINAL — Semantic Runtime v1

## Evidencia ejecutada en esta fase
1. **Import trace del flujo semántico (smoke real):**
   - Script temporal: `tools/trace_imports_semantic.py`
   - Output de módulos importados: `docs/cleanup_audit/imports_used_semantic.txt`

2. **Coverage solicitado sobre test semántico:**
   - Intentado: `pytest -q backend/tests/test_semantic_runtime_v1.py --cov=backend --cov-report=term-missing`
   - Resultado: entorno sin plugin `pytest-cov` (argumentos `--cov` no reconocidos).
   - Evidencia guardada en: `docs/cleanup_audit/coverage_semantic.txt`
   - Fallback ejecutado: `pytest -q backend/tests/test_semantic_runtime_v1.py` (PASS) y anexado al mismo archivo.

3. **Static scan (disponibilidad real):**
   - `ruff check backend` ejecutado, con findings en `docs/cleanup_audit/static_scan_ruff.txt`.
   - `pyflakes` y `vulture` no disponibles en entorno Python (`No module named ...`) en:
     - `docs/cleanup_audit/static_scan_pyflakes.txt`
     - `docs/cleanup_audit/static_scan_vulture.txt`

4. **Inventario backend no importado por el smoke semántico:**
   - Generado en `docs/cleanup_audit/backend_files_not_imported_semantic.txt`
   - Resumen:
     - `backend/*.py` analizados: **162**
     - importados en smoke semántico: **66**
     - NO importados en smoke semántico: **96**

---

## Importante (interpretación correcta)
- “No importado en el smoke semántico” **NO significa automáticamente borrable**: puede ser código de rutas alternativas, API, tooling, o módulos cargados en otros entrypoints/tests.
- Este documento identifica **candidatos** con mayor probabilidad de estar fuera del camino crítico semántico.

---

## Candidatos de mayor prioridad (runtime semántico)

### 1) JUDGE legacy fuera del path activo
- `backend/negotiation/nodes/world_node.py`
  - `_normalize_judgement`
  - `_post_normalize_evidence_guardrails`
  - `_build_evidence_candidates` (+ helpers de evidence)
- Razón: el path activo usa parse semántico directo en `world_judge_llm` (`judge_semantic_v1`) y no llama estas funciones.
- Riesgo: tests legacy (`test_world_judge_contracts.py`) invocan `_normalize_judgement` directamente.
- Estado: **candidato fuerte, Requires test refactor**.

### 2) Planner V2 model stack
- `backend/negotiation/elementos/strategy_definitions.py`
  - `PlannerV2DecisionModel` y submodelos V2
- Razón: planner activo usa `PlannerSemanticV1DecisionModel`.
- Riesgo: dependencia indirecta en tests/contracts antiguos.
- Estado: **candidato fuerte, Requires refactor**.

### 3) Executor step-driven enforcement residual
- `backend/negotiation/nodes/executor_node.py`
  - `_enforce_executor_instruction`
  - `_instruction_followed`
  - `_register_recent_question` (sobre `plan_ledger`)
- Razón: prompt activo ya usa `planner_semantic_output_json + semantic_ledger_json`; enforcement step-driven queda como compat residual.
- Riesgo: tests legacy y modo de compat.
- Estado: **candidato fuerte, Requires refactor**.

### 4) Policy progress bridge residual
- `backend/negotiation/policy_progress.py`
- `backend/negotiation/nodes/policy_progress_node.py`
- Razón: hoy actúa como bridge inocuo, no como motor por `plan_status`.
- Riesgo: contrato de estado y secuencia del grafo.
- Estado: **candidato medio, Requires graph/state refactor**.

### 5) Progress updater legacy engine
- `backend/negotiation/progress_updater.py`
  - `plan_ledger`, `loop_flags`, `same_step_no_progress_turns`, decay blocked topics
- Razón: memoria principal semántica ya es `semantic_ledger`; lo demás es arrastre legacy/telemetría.
- Riesgo: tests numerosos e invariantes de trace.
- Estado: **candidato fuerte, Requires refactor por fases**.

---

## Archivos de backend NO importados por el smoke semántico
Lista completa: `docs/cleanup_audit/backend_files_not_imported_semantic.txt`.

Lectura recomendada:
1. Priorizar `backend/negotiation/**` de esa lista.
2. Excluir de borrado automático módulos de API/app, tooling y tests.
3. Cruzar contra callsites con `rg -n` antes de borrar.

---

## Funciones “nunca tocadas” / 0% coverage en esta fase
- **No disponible con precisión de líneas** por ausencia de `pytest-cov`/`coverage` en entorno.
- Proxy usado:
  - Import trace real del smoke semántico.
  - Findings de `ruff` (incluye imports no usados y patrones sospechosos).
- Acción pendiente antes de borrado físico:
  1. Ejecutar cobertura con plugin disponible.
  2. Confirmar que cada candidato no participa en otros entrypoints (API/UI/jobs).

---

## Riesgos transversales de borrado
- **Alto**: módulos tocados por tests legacy activos.
- **Medio**: contratos de estado (`progress_state`, trace payloads) consumidos por UI/debug.
- **Bajo**: prompts/modelos legacy no importados en runtime y solo retenidos por snapshots/documentación.

---

## Orden sugerido de borrado (sin implementar aquí)
1. Retirar primero exports/prompts legacy no usados en runtime (manteniendo snapshot en docs).
2. Desactivar enforcement step-driven del executor detrás de modo legacy explícito.
3. Limpiar Judge legacy helpers y tests asociados.
4. Reducir `progress_updater` legacy (`plan_ledger/counters`) a telemetría o eliminar.
5. Remover modelos/schema V2 cuando no queden consumidores.
