# Verification Pack — LiveTrace Findings Implementation

## Índice
- `V01_P0_ledger_sync_effective_semantic_ledger.md`
- `V02_LiveTrace2_ledger_hash_observability.md`
- `V03_World_state_deprecation_in_executor_prompt.md`
- `V04_World_Judge_prompt_upgrade_semantic_ledger_quality.md`
- `V05_Summarizer_prompt_upgrade_memory_long_and_novelty.md`
- `V06_Planner_prompt_priority_stack_human_first_rhythm_progress_edge.md`
- `V07_Executor_prompt_priority_stack_human_first_no_repeat_rhythm_yield_progress_pushback_edge.md`
- `V08_Persona_trait_change_avoid_always_question.md`
- `V09_Phase_map_discovery_allows_answer_and_yield_mode.md`
- `V10_Replay_suite_and_tests_evidence.md`
- `V11_Known_risks_inconsistencies_duplicates_and_token_pressure.md`
- `V12_Executor_prompt_compaction_second_pass.md`
- `V13_Word_cap_updated_to_40.md`
- `V14_Summary_prompt_deduplicated.md`
- `V15_Objective_summary_spanish_only.md`

## Qué se verificó
1. P0 ledger sync: fuente única `effective_semantic_ledger` para planner/executor.
2. Hashes y observabilidad de mismatch en debug trace y LiveTrace2.
3. Deprecación de dependencia principal en `world_json` en prompt executor.
4. Upgrade de prompt world judge (calidad de ledger semántico).
5. Upgrade de prompt summary (memoria larga + novedad/no repetición).
6. Stack de prioridades del planner (human-first, ritmo, progreso, pushback, edge).
7. Stack de prioridades del executor (human-first, no-repeat, ritmo, ceder iniciativa, progreso, pushback, picardía).
8. Cambio de trait persona para romper sesgo “preguntar siempre”.
9. Ajuste de `phase_map` para discovery con modo “responder y ceder”.
10. Evidencia práctica con tests y replay suite.
11. Riesgos conocidos de consistencia/duplicidad/presión de tokens.

## Cómo reproducir (mínimo)
```bash
pytest -q backend/tests/test_semantic_runtime_v1.py backend/tests/test_livetrace2_stream.py
python scripts/replay_behavior_suite.py
rg -n "effective_semantic_ledger|planner_ledger_hash|executor_ledger_hash|effective_ledger_hash|ledger_mismatch_detected" backend/negotiation
rg -n "LEGACY_OPTIONAL_WORLD_JSON|WORLD_COMPLETO_JSON|BELIEF_COMPLETO_JSON" backend/negotiation/elementos/render/executor_prompts.py
rg -n "REGLAS_MEMORIA_LARGA|NOVEDAD_Y_REPETICION|SEMANTIC_LEDGER_QUALITY_RULES" backend/prompts.py
```

## Checklist de aprobación (DoD) por área
- [ ] V01: planner/executor leen la misma fuente de ledger en turno.
- [ ] V02: hashes visibles en trace y LiveTrace2; mismatch solo métrico.
- [ ] V03: `world_json` marcado como legacy optional en prompt executor.
- [ ] V04: `WORLD_JUDGE_V3_USER_PROMPT` contiene quality rules.
- [ ] V05: `SUMMARY_USER_PROMPT` contiene memoria larga + novedad.
- [ ] V06: planner incluye prioridad completa definida en planes.
- [ ] V07: executor incluye prioridad completa definida en planes.
- [ ] V08: trait persona deja de empujar “one question per turn”.
- [ ] V09: discovery incluye explícitamente “responder y ceder”.
- [ ] V10: tests/replay ejecutados y resultados documentados.
- [ ] V11: riesgos e inconsistencias documentados con evidencia.
- [ ] V12: prompt executor compactado sin duplicidades críticas.
- [ ] V13: `max_words` por defecto subido a 40 en style/prompt/runtime.
- [ ] V14: `SUMMARY_*` deduplicado a una sola definición canónica.
- [ ] V15: `OBJECTIVE_SUMMARY` de fallback en español 100%.
