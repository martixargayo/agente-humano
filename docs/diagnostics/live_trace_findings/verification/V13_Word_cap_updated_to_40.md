# V13 — Word cap default actualizado a 40

## A) Qué se verificó
- `max_words` de estilo psyplay compact sube de 30 a 40.
- `_WORD_CAP_LIMIT` default sube a 40 con env override intacto.
- Schema textual del executor refleja `max_words=40`.

## B) Evidencia reproducible
```bash
rg -n "max_words":\ 40|max_words=40|_WORD_CAP_LIMIT = int\(os.getenv\("NEGOTIATION_EXECUTOR_WORD_CAP", "40"\)" backend/negotiation/elementos/render/carlos_buyer_preset.py backend/negotiation/elementos/render/executor_prompts.py backend/negotiation/executor/render_executor.py
python scripts/dump_literal_prompts.py
```

## C) Resultado esperado
- Matches en los tres archivos.
