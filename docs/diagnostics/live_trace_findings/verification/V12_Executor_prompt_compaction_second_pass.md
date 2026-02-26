# V12 — Executor prompt compaction (segunda pasada)

## A) Qué se verificó
- Se eliminó duplicidad de bloques human-first.
- Se fusionó no-repetición literal + no-repetición por idea en un bloque único.
- Se redujo el bloque de canal a versión compacta (regla + 2–3 ejemplos + self-check).

## B) Evidencia reproducible
```bash
rg -n "HUMAN_FIRST_Y_RITMO|COMMON_SENSE_HUMAN_FIRST|MEMORIA_Y_NO_REPETICION|SEMANTIC_LEDGER_Y_NO_REPETICION|NO-REPEAT BY IDEA|CANAL_SOLO_TEXTO" backend/negotiation/elementos/render/executor_prompts.py
python scripts/dump_literal_prompts.py
```

## C) Resultado esperado
- Presencia: `HUMAN_FIRST_Y_RITMO`, `MEMORIA_Y_NO_REPETICION`, `CANAL_SOLO_TEXTO`.
- Ausencia: `COMMON_SENSE_HUMAN_FIRST`, `SEMANTIC_LEDGER_Y_NO_REPETICION`, `NO-REPEAT BY IDEA` como bloques separados.

## D) Riesgo residual
- El prompt sigue extenso; posible fatiga de instrucciones en modelos pequeños.
