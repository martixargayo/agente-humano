# V-PROMPT-05 — Effective semantic ledger en prompts

## A) Prompt literal renderizado

### Planner — bloque `SEMANTIC_LEDGER_JSON`
```text
{"lo_que_ya_se_toco": ["estado general", "mantenimiento", "motivo de venta"], "lo_que_ya_pregunte": ["mantenimiento", "precio"], "lo_que_falta_pero_no_insistire": ["kilometraje exacto"]}
```

### Executor — bloque `SEMANTIC_LEDGER_JSON`
```text
{"lo_que_ya_se_toco": ["estado general", "mantenimiento", "motivo de venta"], "lo_que_ya_pregunte": ["mantenimiento", "precio"], "lo_que_falta_pero_no_insistire": ["kilometraje exacto"]}
```

## B) Dónde se renderiza
- Planner: `backend/negotiation/phase_policy_planner.py`
- Executor: `backend/negotiation/executor/render_executor.py`

## C) Payload/messages al LLM
- Ambos bloques provienen de `HumanMessage(content=...)` capturado en `prompt_capture.json`.

## D) Evidencia reproducible
```bash
python scripts/dump_literal_prompts.py
python - <<'PY'
import json,re
obj=json.load(open('docs/diagnostics/live_trace_findings/verification_prompts_literal/prompt_capture.json'))
pp=obj['runtime']['planner']['input_prompt_rendered']
ep=obj['runtime']['executor']['input_prompt_rendered']
print(re.search(r'SEMANTIC_LEDGER_JSON:\s*(\{.*?\})\nPHASE_MAP_JSON', pp, re.S).group(1))
print(re.search(r'C\) SEMANTIC_LEDGER_JSON \(MEMORIA TÁCTICA\)\n(\{.*?\})\n\nD\)', ep, re.S).group(1))
print(obj['runtime']['trace'])
PY
```

## E) Confirmación de hash
- planner_ledger_hash: `e6b5a4ca5653b67719045d6f8cb44e98c9d7911d26ad44dc0503099693d7e3e0`
- executor_ledger_hash: `e6b5a4ca5653b67719045d6f8cb44e98c9d7911d26ad44dc0503099693d7e3e0`
- effective_ledger_hash: `e6b5a4ca5653b67719045d6f8cb44e98c9d7911d26ad44dc0503099693d7e3e0`
- ledger_mismatch_detected: `False`
