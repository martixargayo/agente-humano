# Auditoría EXECUTOR — semantic runtime v1

## 1) Prompt activo

Archivo: `backend/negotiation/elementos/render/executor_prompts.py`

### Confirmaciones
- **Ya NO contiene**:
  - `executor_instruction_json`
  - `planner_output_summary` legacy
- **Sí contiene**:
  - `planner_semantic_output_json`
  - `semantic_ledger_json`
  - `assistant_last_message`
  - `recent_history_text`

Además mantiene:
- contrato `executor_v2`
- límites de salida (`max_words/max_questions`)
- prohibición explícita de acciones físicas/no textuales

## 2) Wiring en `render_executor_output`

Archivo: `backend/negotiation/executor/render_executor.py`

Evidencia de origen de datos:
- `planner_semantic_output = state.get("planner_semantic_output") ...`
- `semantic_ledger = ((state.get("progress_state") or {}).get("semantic_ledger") ...)`

Evidencia de inyección al prompt:
- `planner_semantic_output_json=json.dumps(planner_semantic_output, ...)`
- `semantic_ledger_json=json.dumps(semantic_ledger, ...)`
- `assistant_last_message=str(state.get("assistant_last_message", "") or "")`
- `recent_history_text=str(state.get("recent_history_text", "") or "")`

### Dependencia de `strategy_summary.executor_instruction`
- En el assembly actual del prompt activo: **no se inyecta** `executor_instruction_json`.
- Por tanto, el prompt semántico no depende de step-instruction legacy como input central.

## 3) Enforcement activo / inactivo

### Activo
1. `safe_json_load` + `normalize_executor_output`
2. `_enforce_executor_v2_contract`:
   - respeta `StyleContract` (`max_words`, `max_questions`)
   - sanea formato
   - asegura consistencia `asked_question/requested_info_slots`
3. Reglas del system prompt de canal seguro (sin acciones físicas/documentales a mostrar/enviar)

### Inactivo o de impacto reducido frente a step-driven
- El prompt ya no exige step final question.
- `_build_retry_hint` quedó neutro (`return ""`), removiendo dependencia operacional en `plan_status`.

### Observación importante
- En `executor_node.py` aún existe enforcement de instrucción (`_enforce_executor_instruction`, `_instruction_followed`).
- En práctica, como `state["executor_instruction"] = {}` en planner node semántico, ese enforcement no gobierna el flujo.

## 4) Caso demostrativo “NO repetir motivo de venta”

### Input conceptual
- `progress_state.semantic_ledger.lo_que_ya_pregunte` contiene: “Pregunté por qué lo vende.”
- `planner_semantic_output.what_not_to_repeat` incluye: “No volver a preguntar por qué lo vende.”

### Comportamiento esperado del executor
- Responder breve/validar.
- No reabrir la pregunta “¿por qué lo vendes?”.
- Si pregunta algo, debe ser 0 o 1 pregunta y distinta del tema marcado.

## 5) Checklist EXECUTOR PASS/FAIL

- [PASS] Prompt activo incluye `planner_semantic_output_json + semantic_ledger_json + assistant_last_message + recent_history_text`.
- [PASS] Prompt activo ya no contiene `executor_instruction_json`.
- [PASS] Wiring de render obtiene planner_semantic_output/ledger directamente del state.
- [PASS] Enforcement principal mantiene solo determinismo permitido (schema + style limits + seguridad canal).
- [NEEDS_FIX/P0] Inconsistencia de clave: render usa `assistant_last_message`, graph setea `last_assistant_message`.
- [PASS con nota] Enforcement step-driven existe en `executor_node`, pero queda neutralizado al no haber instrucción step en runtime semántico.
