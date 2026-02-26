# V14 — SUMMARY prompt deduplicado

## A) Qué se verificó
- `backend/prompts.py` ahora tiene una sola definición de `SUMMARY_SYSTEM_PROMPT` y una sola de `SUMMARY_USER_PROMPT`.
- `backend/agent.py` sigue consumiendo el prompt correcto de summary.

## B) Evidencia reproducible
```bash
rg -n "^SUMMARY_SYSTEM_PROMPT\s*=|^SUMMARY_USER_PROMPT\s*=" backend/prompts.py
rg -n "summary_prompt\.format_messages|summary_llm\.invoke" backend/agent.py
python scripts/dump_literal_prompts.py
```

## C) Resultado esperado
- 1 match para `SUMMARY_SYSTEM_PROMPT`.
- 1 match para `SUMMARY_USER_PROMPT`.
