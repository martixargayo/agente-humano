# V15 — OBJECTIVE_SUMMARY español-only

## A) Qué se verificó
- `build_objective_summary` devuelve plantilla estable 100% español cuando no hay objetivo explícito.
- Ya no depende de `macro_goal/goals` potencialmente en inglés.

## B) Evidencia reproducible
```bash
rg -n "def build_objective_summary|Objetivo: evaluar el coche, minimizar riesgo y negociar" backend/negotiation/llm_planning_context.py
python scripts/dump_literal_prompts.py
python - <<'PY'
import json,re
obj=json.load(open('docs/diagnostics/live_trace_findings/verification_prompts_literal/prompt_capture.json'))
pp=obj['runtime']['planner']['input_prompt_rendered']
m=re.search(r'OBJECTIVE_SUMMARY:\s*(.*)\nFULL_PROFILES_BLOCK',pp,re.S)
print(m.group(1).strip() if m else 'N/A')
PY
```

## C) Resultado esperado
- `OBJECTIVE_SUMMARY` aparece en español sin texto base en inglés.
