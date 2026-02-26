# V04 — World Judge prompt upgrade (semantic ledger quality)

## A) Qué se afirma que cambió
- El prompt de world judge ahora incluye reglas explícitas de calidad para construir ledger semántico útil.
- Se mantiene el contrato de salida `judge_semantic_v1` sin cambios estructurales.
- Se prioriza captura por ideas accionables y no por literalidad.

## B) Dónde está en el repo (rutas + símbolos)
- `backend/prompts.py`
  - `WORLD_JUDGE_V3_USER_PROMPT`
- `backend/negotiation/nodes/world_node.py`
  - `world_judge_llm` usa `WORLD_JUDGE_V3_USER_PROMPT`

## C) Evidencia 1 — Diff / Snippets (con contexto)
```text
# backend/prompts.py
SEMANTIC_LEDGER_QUALITY_RULES:
- Captura IDEAS, no frases literales.
- Normaliza en lenguaje breve y útil para conversación futura.
- Prioriza: (a) lo ya tratado, (b) preguntas ya hechas por el asistente,
  (c) temas que el usuario no quiere seguir forzando.
- Evita ruido descriptivo irrelevante; privilegia memoria accionable para el siguiente turno.
```

```text
Devuelve SOLO JSON con:
- schema_version: "judge_semantic_v1"
- topic_alignment: "on_topic" | "off_topic"
- reason_short: string
- semantic_ledger: objeto con listas
- ledger_update_notes: string
```

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "SEMANTIC_LEDGER_QUALITY_RULES|WORLD_JUDGE_V3_USER_PROMPT|judge_semantic_v1" backend/prompts.py backend/negotiation/nodes/world_node.py
```

## E) Evidencia 3 — Runtime / Prompt rendering
- `world_judge_llm` construye `user_prompt = WORLD_JUDGE_V3_USER_PROMPT.format(...)` y lo envía al LLM.
- Se puede observar en `judge_input_prompt_rendered` dentro de trace runtime.

## F) Evidencia 4 — Telemetría / LiveTrace2
- `world_judge_meta.judge_input_prompt_rendered` y `judge_output_payload_raw` se capturan en runtime y se reflejan en nodo world_judge del evento.

## G) Qué podría estar mal / riesgos detectados
- Riesgo: prompt más largo puede aumentar tokens/latencia del judge.
- Riesgo: si el modelo ignora parcialmente reglas, calidad de ledger seguirá variable.
- Propuesta: medir `ledger_update_notes` calidad con evaluación semántica offline.

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] El prompt contiene `SEMANTIC_LEDGER_QUALITY_RULES`.
- [ ] El contrato de salida `judge_semantic_v1` se mantiene.
- [ ] El world node usa ese prompt en runtime.

Reproducción:
```bash
rg -n "SEMANTIC_LEDGER_QUALITY_RULES|judge_semantic_v1" backend/prompts.py
rg -n "WORLD_JUDGE_V3_USER_PROMPT" backend/negotiation/nodes/world_node.py
```
