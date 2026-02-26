# V03 — Deprecación world_state en prompt executor

## A) Qué se afirma que cambió
- `WORLD_COMPLETO_JSON` dejó de ser bloque principal de decisión en prompt executor.
- `world_json` se conserva por compat como `LEGACY_OPTIONAL_WORLD_JSON`.
- La prioridad del prompt ahora enfatiza `semantic_ledger` + `memory_long`.

## B) Dónde está en el repo (rutas + símbolos)
- `backend/negotiation/elementos/render/executor_prompts.py`
  - `EXECUTOR_V2_USER_PROMPT`
- `backend/negotiation/executor/render_executor.py`
  - inyección de `world_json` (compat)

## C) Evidencia 1 — Diff / Snippets (con contexto)
```text
# backend/negotiation/elementos/render/executor_prompts.py
I) BELIEF_COMPLETO_JSON (SOLO LECTURA)
{belief_json}

J) LEGACY_OPTIONAL_WORLD_JSON (solo compat, NO usar como fuente principal)
{world_json}
```

```text
Instrucciones de prioridad:
- Prioriza: user_message + last_counterparty_utterance + planner_semantic_output_json + semantic_ledger_json + memory_long.
- Usa world_json solo como compatibilidad opcional, nunca como fuente principal de decisión.
```

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "LEGACY_OPTIONAL_WORLD_JSON|WORLD_COMPLETO_JSON|BELIEF_COMPLETO_JSON" backend/negotiation/elementos/render/executor_prompts.py
```
Salida esperada: `LEGACY_OPTIONAL_WORLD_JSON` y `BELIEF_COMPLETO_JSON`; `WORLD_COMPLETO_JSON` ya no aparece.

## E) Evidencia 3 — Runtime / Prompt rendering
- `render_executor_output` sigue inyectando `world_json`, pero el prompt lo marca explícitamente como compat no principal.
- Para validarlo en runtime se puede capturar `executor_llm.input_prompt_rendered` (tests de runtime ya capturan prompt).

## F) Evidencia 4 — Telemetría / LiveTrace2
- No agrega campo nuevo específico para world deprecation; se verifica por prompt render.

## G) Qué podría estar mal / riesgos detectados
- Riesgo: etiqueta I/J puede confundir si consumidores externos esperaban posición fija de bloques.
- Riesgo menor: mantener `world_json` podría seguir influyendo si modelo ignora nota de “legacy”.
- Propuesta: en fase posterior, reducir aún más el detalle de `world_json` inyectado.

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] `LEGACY_OPTIONAL_WORLD_JSON` aparece en prompt executor.
- [ ] `WORLD_COMPLETO_JSON` desaparece del prompt executor.
- [ ] Prioridades incluyen `memory_long`.

Reproducción:
```bash
rg -n "LEGACY_OPTIONAL_WORLD_JSON|WORLD_COMPLETO_JSON|memory_long" backend/negotiation/elementos/render/executor_prompts.py
```
