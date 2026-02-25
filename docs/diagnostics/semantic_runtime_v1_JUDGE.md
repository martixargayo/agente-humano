# Auditoría JUDGE — semantic runtime v1

## 1) Código activo (ruta real)

Archivos y funciones clave:
- `backend/negotiation/nodes/world_node.py`
  - `world_judge_llm(...)` (path semántico activo)
  - `_normalize_semantic_ledger(...)`
  - `_semantic_judge_fallback(...)`
- `backend/prompts.py`
  - `WORLD_JUDGE_V3_SYSTEM_PROMPT`
  - `WORLD_JUDGE_V3_USER_PROMPT`
- `backend/negotiation/repo_prompts.py`
  - export de `WORLD_JUDGE_V3_*`

## 2) Prompt activo en runtime

En `world_judge_llm(...)` se construye:
- `SystemMessage(content=WORLD_JUDGE_V3_SYSTEM_PROMPT)`
- `HumanMessage(content=user_prompt)` donde `user_prompt = WORLD_JUDGE_V3_USER_PROMPT.format(...)`

Inputs inyectados (mínimos semánticos):
- `user_message`
- `assistant_last_message`
- `recent_history_text`
- `semantic_ledger_prev`
- `speaker_of_last_message`

## 3) Prueba de que NO corre legacy normalizer/evidence en path activo

Evidencia directa:
- En `world_judge_llm(...)` el parse activo hace:
  - `candidate = json.loads(text)`
  - check `schema_version == "judge_semantic_v1"`
  - check `topic_alignment in {"on_topic","off_topic"}`
  - normaliza solo `semantic_ledger` vía `_normalize_semantic_ledger(...)`
- No hay llamada a:
  - `_normalize_judgement(...)`
  - `_post_normalize_evidence_guardrails(...)`

Verificación por referencia cruzada:
- Ambos símbolos aparecen como `def` en el archivo, pero no tienen callsite en el path actual (`rg` solo devuelve definiciones).

## 4) Prueba de persistencia en state

- En `_apply_judge_advisor_results(...)`:
  - `state["semantic_judge"] = judgement`
- Luego, `progress_updater_node` pasa ese valor a `update_progress_state(..., semantic_judge=...)`.
- En `update_progress_state(...)`:
  - normaliza ledger previo
  - fusiona `semantic_judge["semantic_ledger"]`
  - persiste en `progress["semantic_ledger"]`

## 5) Posibles fallos detectados

1. **P0: clave de contexto inconsistente (`assistant_last_message` vs `last_assistant_message`)**
   - Judge usa `state.get("last_assistant_message", "")` (correcto con graph actual).
   - Pero planner/executor consumen `assistant_last_message` en varios puntos.

2. **P0: import de prompts con ruta absoluta**
   - Judge no sufre esto directamente (usa `repo_prompts`), pero el runtime global sí tiene módulos con `from prompts import ...`.

3. **P1: compat inerte en `policy_plan_judgement`**
   - Se persiste `schema_version="v1_compat_inert"`; tooling estricto de v1 podría no aceptarlo.

## 6) Mini test manual reproducible (caso “¿por qué lo vendes?”)

### Input de turno (ejemplo)
- `assistant_last_message`: “¿Por qué lo vendes?”
- `user_message`: “La verdad, ya no lo uso.”
- `recent_history_text`: últimos 1–3 turnos.
- `semantic_ledger_prev`: listas previas (o vacías).

### Output esperado del judge (shape)
```json
{
  "schema_version": "judge_semantic_v1",
  "topic_alignment": "on_topic",
  "reason_short": "Respuesta alineada con la pregunta del motivo de venta.",
  "semantic_ledger": {
    "lo_que_ya_se_toco": [
      "Motivo de venta tratado: ya no lo usa."
    ],
    "lo_que_ya_pregunte": [
      "Pregunté por qué lo vende."
    ],
    "lo_que_falta_pero_no_insistire": []
  },
  "ledger_update_notes": "Actualización semántica del turno completada."
}
```

## 7) Checklist JUDGE PASS/FAIL

- [PASS] Se ejecuta `WORLD_JUDGE_V3_*` en runtime.
- [PASS] Parse mínimo `judge_semantic_v1` (schema/topic_alignment/ledger).
- [PASS] No pasa por `_normalize_judgement` ni `_post_normalize_evidence_guardrails` en path activo.
- [PASS] Se guarda en `state["semantic_judge"]`.
- [PASS] Se persiste después en `progress_state.semantic_ledger`.
- [NEEDS_FIX/P1] `policy_plan_judgement` compat inerte usa schema_version no estándar (`v1_compat_inert`).
