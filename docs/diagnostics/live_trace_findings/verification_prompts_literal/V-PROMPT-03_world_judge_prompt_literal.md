# V-PROMPT-03 — World Judge prompt literal

## A) Prompt literal renderizado (completo)

### Dump capturado ([system] + [human])
```text
[system]
Eres WORLD_JUDGE_V3, un scribe semántico conversacional.
Devuelve SOLO JSON válido con schema `judge_semantic_v1`.
No incluyas campos extra.

[human]
USER_MESSAGE: "¿Por qué te interesa este coche y qué estarías dispuesto a ofrecer?"
ASSISTANT_LAST_MESSAGE: ""
RECENT_HISTORY_TEXT: "user: ¿Por qué te interesa este coche y qué estarías dispuesto a ofrecer?"
SEMANTIC_LEDGER_PREV: {"lo_que_ya_se_toco": [], "lo_que_ya_pregunte": [], "lo_que_falta_pero_no_insistire": []}
SPEAKER_OF_LAST_MESSAGE: seller

SEMANTIC_LEDGER_QUALITY_RULES:
- Captura IDEAS, no frases literales.
- Normaliza en lenguaje breve y útil para conversación futura.
- Prioriza: (a) lo ya tratado, (b) preguntas ya hechas por el asistente,
  (c) temas que el usuario no quiere seguir forzando.
- Evita ruido descriptivo irrelevante; privilegia memoria accionable para el siguiente turno.

Devuelve SOLO JSON con:
- schema_version: "judge_semantic_v1"
- topic_alignment: "on_topic" | "off_topic"
- reason_short: string
- semantic_ledger: objeto con listas
- ledger_update_notes: string
```

## B) Dónde se renderiza
- Archivo: `backend/negotiation/nodes/world_node.py`
- Función: `world_judge_llm(...)`
- Snippet:
```python
user_prompt = WORLD_JUDGE_V3_USER_PROMPT.format(...)
messages = [SystemMessage(content=WORLD_JUDGE_V3_SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
rendered_prompt = ...
```

## C) Payload/messages al LLM
- `SystemMessage(content=WORLD_JUDGE_V3_SYSTEM_PROMPT)`
- `HumanMessage(content=user_prompt)`

## D) Evidencia reproducible
```bash
python scripts/dump_literal_prompts.py
python - <<'PY'
import json
obj=json.load(open('docs/diagnostics/live_trace_findings/verification_prompts_literal/prompt_capture.json'))
print(obj['runtime']['world_judge']['judge_input_prompt_rendered'])
PY
```

## E) Confirmación de “no duplicados”
- `SEMANTIC_LEDGER_QUALITY_RULES`: count=1
