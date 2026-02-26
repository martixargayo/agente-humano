# V06 — Planner prompt priority stack (human-first, rhythm, progress, edge)

## A) Qué se afirma que cambió
- El planner prompt incluye un stack amplio de prioridades conversacionales/negociadoras.
- Se agregaron bloques: `HUMAN_FIRST_PRIORITY`, `RHYTHM_GUIDE`, `TURN_TAKING_PRIORITY`, `IDEA_LEVEL_NO_REPEAT`, `PROGRESO_NEGOCIADOR`, `BUYER_INTENT`, `PUSHBACK_PRICE_PRIORITY`, `NEGOTIATION_EDGE`.
- El schema de salida del planner se mantiene igual (`phase`, `style`, `next_move_hint`, `what_not_to_repeat`).

## B) Dónde está en el repo (rutas + símbolos)
- `backend/prompts.py`
  - `PLANNER_SEMANTIC_V1_USER_PROMPT`
- `backend/negotiation/phase_policy_planner.py`
  - render de prompt y structured invoke

## C) Evidencia 1 — Diff / Snippets (con contexto)
```text
# backend/prompts.py
HUMAN_FIRST_PRIORITY:
...
RHYTHM_GUIDE:
...
TURN_TAKING_PRIORITY:
...
IDEA_LEVEL_NO_REPEAT:
...
PROGRESO_NEGOCIADOR:
...
BUYER_INTENT:
...
PUSHBACK_PRICE_PRIORITY:
...
NEGOTIATION_EDGE:
...
```

```python
# backend/negotiation/phase_policy_planner.py
user_prompt = PLANNER_SEMANTIC_V1_USER_PROMPT.format(...)
messages = [
    SystemMessage(content=PLANNER_SEMANTIC_V1_SYSTEM_PROMPT),
    HumanMessage(content=user_prompt),
]
result = structured.invoke(messages)
```

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "HUMAN_FIRST_PRIORITY|RHYTHM_GUIDE|TURN_TAKING_PRIORITY|IDEA_LEVEL_NO_REPEAT|PROGRESO_NEGOCIADOR|BUYER_INTENT|PUSHBACK_PRICE_PRIORITY|NEGOTIATION_EDGE" backend/prompts.py
```

## E) Evidencia 3 — Runtime / Prompt rendering
- El test `test_runtime_prompts_include_objective_profiles_phase_map_and_memory` valida que planner prompt se renderiza y captura en runtime.
- No existe assert específico por cada bloque nuevo; evidencia actual es inspección del prompt renderizado en trace.

## F) Evidencia 4 — Telemetría / LiveTrace2
- `planner_llm.input_prompt_rendered` se captura en `trace_runtime.llm_calls`, accesible desde payload.

## G) Qué podría estar mal / riesgos detectados
- Riesgo: crecimiento de prompt y dilución de prioridades por longitud.
- Riesgo: instrucciones superpuestas (human-first + progress + edge) podrían competir.
- Propuesta: monitorizar tokens y consistencia semántica por ablations (sin gates).

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] Todos los bloques están en prompt del planner.
- [ ] Planner sigue usando este prompt en runtime.
- [ ] Schema de salida no cambia.

Reproducción:
```bash
rg -n "PLANNER_SEMANTIC_V1_USER_PROMPT|HUMAN_FIRST_PRIORITY|NEGOTIATION_EDGE" backend/prompts.py
rg -n "PLANNER_SEMANTIC_V1_USER_PROMPT.format|structured.invoke" backend/negotiation/phase_policy_planner.py
```
