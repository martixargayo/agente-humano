# verification_prompts_literal

## Índice
- [V-PROMPT-01_planner_prompt_literal.md](./V-PROMPT-01_planner_prompt_literal.md)
- [V-PROMPT-02_executor_prompt_literal.md](./V-PROMPT-02_executor_prompt_literal.md)
- [V-PROMPT-03_world_judge_prompt_literal.md](./V-PROMPT-03_world_judge_prompt_literal.md)
- [V-PROMPT-04_summarizer_prompt_literal.md](./V-PROMPT-04_summarizer_prompt_literal.md)
- [V-PROMPT-05_effective_ledger_in_prompt_literal.md](./V-PROMPT-05_effective_ledger_in_prompt_literal.md)

## Comandos para reproducir
```bash
python scripts/dump_literal_prompts.py
python - <<'PY'
import json
obj=json.load(open('docs/diagnostics/live_trace_findings/verification_prompts_literal/prompt_capture.json'))
print('planner chars', len(obj['runtime']['planner']['input_payload_raw'][1]['content']))
print('executor chars', len(obj['runtime']['executor']['input_payload_raw'][1]['content']))
print('world chars', len(obj['runtime']['world_judge']['judge_input_prompt_rendered']))
print('summary msgs', len(obj['summary']['messages']))
PY
```
