# V07 — Executor prompt priority stack (human-first + no-repeat + rhythm + yield + progress + pushback + edge)

## A) Qué se afirma que cambió
- El `EXECUTOR_V2_SYSTEM_PROMPT` incorporó el stack priorizado completo solicitado.
- Se añadieron bloques para human-first, no-repeat por idea, anti-interrogatorio, ceder iniciativa, progreso por turno, pushback de precio y picardía respetuosa.
- El executor mantiene libertad para `asked_question=false` y no fuerza pregunta.

## B) Dónde está en el repo (rutas + símbolos)
- `backend/negotiation/elementos/render/executor_prompts.py`
  - `EXECUTOR_V2_SYSTEM_PROMPT`
- `backend/negotiation/executor/render_executor.py`
  - `normalize_executor_output` (admite `asked_question=False`)
- `scripts/replay_behavior_suite.py`
  - salidas observacionales de casos

## C) Evidencia 1 — Diff / Snippets (con contexto)
```text
# backend/negotiation/elementos/render/executor_prompts.py
[HUMAN-FIRST PRIORITY — APLICACIÓN]
[NO-REPEAT BY IDEA]
[RITMO_ANTI_INTERROGATORIO — PRIORIDAD]
[CEDER_INICIATIVA — PRIORIDAD HUMANA]
[PROGRESO_POR_TURNO]
[PRICE_PUSHBACK — PRIORIDAD CONVERSACIONAL]
[PICARDIA_RESPETUOSA]
```

```python
# backend/negotiation/executor/render_executor.py
base = {
  "asked_question": False,
  "requested_info_slots": [],
}
...
out["asked_question"] = asked_question
```

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "HUMAN-FIRST PRIORITY|NO-REPEAT BY IDEA|RITMO_ANTI_INTERROGATORIO|CEDER_INICIATIVA|PROGRESO_POR_TURNO|PRICE_PUSHBACK|PICARDIA_RESPETUOSA" backend/negotiation/elementos/render/executor_prompts.py
rg -n "asked_question": backend/negotiation/executor/render_executor.py
```

## E) Evidencia 3 — Runtime / Prompt rendering
- Replay suite actual reporta `question_turn_rate=0.0` en los casos incluidos (evidencia de capacidad de cerrar sin pregunta).
- Casos incluidos: direct question, price pushback, paraphrase repeat.

## F) Evidencia 4 — Telemetría / LiveTrace2
- `executor_output` se serializa en trace y evento; permite inspeccionar `asked_question` y contenido final.

## G) Qué podría estar mal / riesgos detectados
- Riesgo: prompt system del executor puede estar demasiado largo y con bloques potencialmente redundantes.
- Riesgo: coexisten bloques de prioridad nuevos y bloque legacy `COMMON_SENSE_HUMAN_FIRST`, posible duplicidad semántica.
- Propuesta: consolidación por prioridad en una pasada posterior (sin perder filosofía LLM-first).

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] Todos los bloques nuevos aparecen en system prompt executor.
- [ ] El executor puede responder con `asked_question=false`.
- [ ] Replay muestra casos sin interrogatorio continuo.

Reproducción:
```bash
python scripts/replay_behavior_suite.py
rg -n "RITMO_ANTI_INTERROGATORIO|PRICE_PUSHBACK|PICARDIA_RESPETUOSA" backend/negotiation/elementos/render/executor_prompts.py
```
