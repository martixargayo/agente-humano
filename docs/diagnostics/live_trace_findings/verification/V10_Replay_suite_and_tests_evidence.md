# V10 — Evidencia práctica: tests + replay suite

## A) Qué se afirma que cambió
- La suite de tests relevante sigue pasando tras los cambios.
- Se añadieron tests específicos de ledger sync/observabilidad.
- Existe replay suite observacional para métricas de ritmo, pushback y repetición semántica.

## B) Dónde está en el repo (rutas + símbolos)
- `backend/tests/test_semantic_runtime_v1.py`
  - `test_effective_ledger_is_shared_by_planner_and_executor`
  - `test_trace_exposes_ledger_hash_observability`
- `backend/tests/test_livetrace2_stream.py`
- `scripts/replay_behavior_suite.py`

## C) Evidencia 1 — Diff / Snippets (con contexto)
```python
# backend/tests/test_semantic_runtime_v1.py
assert '"inicio"' in planner_prompt
assert '"inicio"' in executor_prompt
...
assert trace.get("planner_ledger_hash") == trace.get("executor_ledger_hash")
assert trace.get("ledger_mismatch_detected") is False
```

```python
# scripts/replay_behavior_suite.py
return {
  "question_turn_rate": ...,
  "consecutive_question_streak": ...,
  "ledger_mismatch_rate": ...,
}
```

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "test_effective_ledger_is_shared_by_planner_and_executor|test_trace_exposes_ledger_hash_observability" backend/tests/test_semantic_runtime_v1.py
rg -n "question_turn_rate|ledger_mismatch_rate|price_pushback_variant" scripts/replay_behavior_suite.py
```

## E) Evidencia 3 — Runtime / Prompt rendering
Comandos ejecutados:
```bash
pytest -q backend/tests/test_semantic_runtime_v1.py backend/tests/test_livetrace2_stream.py
python scripts/replay_behavior_suite.py
```
Resultados observados:
- `pytest`: 16 tests passed.
- Replay:
  - `turnos_2_18_base`: `question_turn_rate=0.0`, `ledger_mismatch_rate=0.0`
  - `direct_question_variant`: `question_turn_rate=0.0`, `ledger_mismatch_rate=0.0`
  - `price_pushback_variant`: `question_turn_rate=0.0`, `ledger_mismatch_rate=0.0`
  - `paraphrase_repeat_variant`: `question_turn_rate=0.0`, `ledger_mismatch_rate=0.0`

## F) Evidencia 4 — Telemetría / LiveTrace2
- `test_livetrace2_stream.py` sigue pasando, indicando que serialización de eventos trace2 no se rompió.
- Hashes nuevos están en payload model (ver V02).

## G) Qué podría estar mal / riesgos detectados
- Replay suite actual usa dummies y no LLM-judge semántico real.
- Métricas actuales no estiman directamente `ignored_direct_question_rate` ni `idea_repeat_rate` semánticos con juez externo.
- Propuesta mínima futura (sin implementar aquí): añadir runner de evaluación semántica offline con rubricas LLM-judge.

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] Tests pasan.
- [ ] Replay corre y emite métricas.
- [ ] Se pueden reproducir los comandos en entorno local.

Reproducción exacta:
```bash
pytest -q backend/tests/test_semantic_runtime_v1.py backend/tests/test_livetrace2_stream.py
python scripts/replay_behavior_suite.py
```
