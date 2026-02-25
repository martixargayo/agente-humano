# Cleanup candidates — JUDGE

## Source of truth (runtime activo)
- Path activo: `world_updater_node -> _apply_judge_advisor_results -> world_judge_llm`.
- Prompt activo: `WORLD_JUDGE_V3_SYSTEM_PROMPT` + `WORLD_JUDGE_V3_USER_PROMPT`.
- Salida activa: `state["semantic_judge"]` y `policy_plan_judgement` compat inerte (`schema_version: "v1"`).

Evidencia:
- `world_judge_llm` parsea `judge_semantic_v1` y valida `schema_version/topic_alignment/semantic_ledger`.
- `world_updater_node` canonicaliza `assistant_last_message` y ejecuta path semántico.

---

## Candidate J-1
1) **Qué es**
- `backend/negotiation/nodes/world_node.py`
- Funciones: `_normalize_judgement`, `_post_normalize_evidence_guardrails`, `_build_evidence_candidates`, `_normalize_evidence_items`, `_build_evidence_item`.

2) **Por qué parece muerto**
- El parse activo de `world_judge_llm` ya hace validación semántica directa y fallback semántico.
- No hay callsite runtime hacia `_normalize_judgement` ni `_post_normalize_evidence_guardrails`.

3) **Quién lo consumía antes (legacy)**
- Judge V2: `json.loads -> _normalize_judgement -> _post_normalize_evidence_guardrails -> policy_plan_judgement`.

4) **Quién consume ahora (semántico)**
- `world_judge_llm` devuelve `judge_semantic_v1`; `state["semantic_judge"]` se persiste luego en progress.

5) **Riesgo de borrarlo**
- Alto para tests legacy: `backend/tests/test_world_judge_contracts.py` llama `_normalize_judgement` directamente.

6) **Plan de eliminación (sin implementar)**
- Fase 1: migrar o archivar tests `test_world_judge_contracts.py`.
- Fase 2: remover funciones legacy y limpiar imports/helpers asociados.

7) **Clasificación**
- **Quick win** técnico, pero **requiere ajuste de tests**.

---

## Candidate J-2
1) **Qué es**
- Prompt constants legacy:
  - `backend/prompts.py`: `WORLD_JUDGE_V2_SYSTEM_PROMPT`, `WORLD_JUDGE_V2_USER_PROMPT`
  - `backend/negotiation/repo_prompts.py` re-exporta V2.

2) **Por qué parece legacy no activo**
- Path runtime usa V3 en `world_node.py`.
- No hay callsite runtime V2 en `backend/negotiation/**` (solo tests/docs/re-export).

3) **Quién lo consumía antes**
- `world_judge_llm` legacy V2 + contrato `plan_status/evidence/skip_planner`.

4) **Quién consume ahora**
- Solo tests de prompts (`test_judge_advisor_v2_prompts.py`) y documentación de referencia.

5) **Riesgo de borrarlo**
- Rompe tests y posible tooling que inspecciona prompt V2.

6) **Plan de eliminación**
- Marcar V2 como deprecated.
- Migrar tests a snapshot “legacy archive”.
- Eliminar export V2 de `repo_prompts.py`.

7) **Clasificación**
- **Quick win** tras limpieza de tests.

---

## Candidate J-3
1) **Qué es**
- `state["policy_plan_judgement"]` compat inerte generado en `_apply_judge_advisor_results`.

2) **Por qué es candidato (no muerto total)**
- Ya no gobierna planner semántico, pero sigue fluyendo por compat y debug.

3) **Quién lo consumía antes**
- `policy_progress` + gates planner legacy + progress counters.

4) **Quién lo consume ahora**
- `progress_updater` y partes de telemetría/legacy fields.

5) **Riesgo de borrarlo**
- Puede romper invariantes, tests y paneles que esperan la key.

6) **Plan de eliminación**
- Mantener en milestone intermedio como “compat shim”.
- Retirar cuando `progress_updater` y tests de fields legacy sean semánticos puros.

7) **Clasificación**
- **Requires refactor**.
