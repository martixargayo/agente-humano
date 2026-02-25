# LEGACY_PURGE_REPORT

## Resumen
Se ejecutó una purga agresiva para dejar el runtime en modo semantic-only. Se eliminaron tests legacy y se simplificaron módulos runtime para quitar contratos y motores legacy.

---

## Comandos ejecutados y resultado
1. Borrado de tests legacy (manteniendo solo test semántico)
- `find backend/tests -type f ! -name 'test_semantic_runtime_v1.py' -delete`
- Resultado: OK.

2. Verificación de términos legacy prohibidos (final)
- `rg -n "planner_v2|WORLD_JUDGE_V2|PLANNER_V2|plan_status|evidence_candidates|success_criteria|active_plan|executor_instruction|plan_ledger" backend -S`
- Resultado: **0 matches** (rg exit code 1 = sin resultados).

3. Verificación fallback de assistant context
- `rg -n "assistant_last_message|last_assistant_message" backend -S`
- Resultado: fallback y canonicalización presentes en planner/world/executor/graph.

4. Compilación mecánica de módulos tocados
- `python -m py_compile backend/prompts.py backend/negotiation/repo_prompts.py backend/negotiation/schemas.py backend/negotiation/nodes/world_node.py backend/negotiation/phase_policy_planner.py backend/negotiation/nodes/planner_node.py backend/negotiation/progress_updater.py backend/negotiation/nodes/progress_node.py backend/negotiation/executor/render_executor.py backend/negotiation/nodes/executor_node.py backend/negotiation/policy_progress.py backend/negotiation/nodes/policy_progress_node.py backend/negotiation/nodes/belief_node.py backend/negotiation/state/deps.py backend/negotiation/negotiation_graph.py backend/negotiation/validation.py backend/negotiation/world_state_updater.py backend/negotiation/advisor.py backend/negotiation/telemetry/live_trace.py backend/negotiation/telemetry/live_trace2.py backend/negotiation/extractors/world_extractor_v4.py backend/negotiation/elementos/strategy_definitions.py backend/tests/test_semantic_runtime_v1.py tools/trace_imports_semantic.py`
- Resultado: OK.

5. Test suite semántica
- `pytest -q backend/tests/test_semantic_runtime_v1.py`
- Resultado: `6 passed`.

6. Smoke test de 3 turnos (no repregunta motivo en turno 3)
- Script ejecutado con `PYTHONPATH=backend python - <<'PY' ... PY`.
- Evidencia: `docs/cleanup_audit/smoke_semantic_turns.txt`.
- Resultado clave:
  - `turn1_response= Entiendo. ¿Por qué lo vendes?`
  - `turn3_response= Perfecto, gracias. ¿Qué precio tienes pensado ahora?`
  - `no_reask_motivo= True`

---

## Lista exacta de archivos borrados
Se borraron todos los tests legacy bajo `backend/tests/` excepto `test_semantic_runtime_v1.py`, incluyendo:
- `backend/tests/conftest.py`
- `backend/tests/helpers/negotiation_harness.py`
- `backend/tests/legacy_fixtures/belief_contracts_legacy.py`
- `backend/tests/test_api_negotiation_smoke.py`
- `backend/tests/test_app_env_migration.py`
- `backend/tests/test_app_interface_simulation.py`
- `backend/tests/test_belief_backward_compat.py`
- `backend/tests/test_belief_diagnostics_repro.py`
- `backend/tests/test_belief_force_by_backstop.py`
- `backend/tests/test_belief_general_micro_updates.py`
- `backend/tests/test_belief_legacy_consumers_removed.py`
- `backend/tests/test_belief_llm_gating_trace.py`
- `backend/tests/test_belief_node_world_buckets.py`
- `backend/tests/test_belief_normalization_v2.py`
- `backend/tests/test_belief_parse_fallback.py`
- `backend/tests/test_belief_state_migration.py`
- `backend/tests/test_belief_state_v2_schema.py`
- `backend/tests/test_carlos_buyer_preset_executor_prompt.py`
- `backend/tests/test_carlos_buyer_preset_runtime.py`
- `backend/tests/test_clarity_signals_phase.py`
- `backend/tests/test_confidence_guardrails_v3.py`
- `backend/tests/test_constraints_epistemic_contract.py`
- `backend/tests/test_constraints_struct_builder.py`
- `backend/tests/test_control_plane.py`
- `backend/tests/test_conversation_mode_hysteresis.py`
- `backend/tests/test_dead_code_cleanup.py`
- `backend/tests/test_dead_code_precedence_removed.py`
- `backend/tests/test_deferred_summary_jobs.py`
- `backend/tests/test_deps_smoke.py`
- `backend/tests/test_e2e_negotiation_pipeline.py`
- `backend/tests/test_executor_backcompat_text.py`
- `backend/tests/test_executor_intent_hint.py`
- `backend/tests/test_executor_output_shape.py`
- `backend/tests/test_executor_persona_stability.py`
- `backend/tests/test_executor_plan_compliance.py`
- `backend/tests/test_gate_world_voice.py`
- `backend/tests/test_hardening_integration_turns.py`
- `backend/tests/test_hybrid_trace_fields.py`
- `backend/tests/test_imports_compile.py`
- `backend/tests/test_instrumented_planner_skip_consistency.py`
- `backend/tests/test_intent_integration.py`
- `backend/tests/test_interaction_gating.py`
- `backend/tests/test_judge_advisor_v2_prompts.py`
- `backend/tests/test_legacy_guardrails.py`
- `backend/tests/test_live_trace_runtime_wiring.py`
- `backend/tests/test_live_trace_telemetry.py`
- `backend/tests/test_live_trace_vnext_fields.py`
- `backend/tests/test_livetrace2_ui.py`
- `backend/tests/test_livetrace2_v1.py`
- `backend/tests/test_memory_prompt.py`
- `backend/tests/test_negotiation_env_vars.py`
- `backend/tests/test_negotiation_model_config.py`
- `backend/tests/test_negotiation_pipeline_smoke_turns.py`
- `backend/tests/test_negotiation_trace_belief_buckets_compaction.py`
- `backend/tests/test_negotiation_v3_post_migration_guards.py`
- `backend/tests/test_no_legacy_keys_in_negotiation_runtime.py`
- `backend/tests/test_phase_harvard_migration.py`
- `backend/tests/test_phase_logic.py`
- `backend/tests/test_phase_policy_desfase_fix.py`
- `backend/tests/test_phase_policy_minimal_contract.py`
- `backend/tests/test_phase_policy_prompt_format.py`
- `backend/tests/test_plan_ledger.py`
- `backend/tests/test_planner_executor_v2_contract.py`
- `backend/tests/test_policy_planner.py`
- `backend/tests/test_policy_progress_and_planner_invariants.py`
- `backend/tests/test_policy_progress_invariants.py`
- `backend/tests/test_progress_updater.py`
- `backend/tests/test_render_executor_belief_summary.py`
- `backend/tests/test_render_executor_epistemic_contract.py`
- `backend/tests/test_render_profiles_defaults.py`
- `backend/tests/test_render_profiles_override.py`
- `backend/tests/test_response_validator.py`
- `backend/tests/test_state_migration_v3.py`
- `backend/tests/test_state_normalization.py`
- `backend/tests/test_temporal_invariant.py`
- `backend/tests/test_validator_critical_fallback.py`
- `backend/tests/test_validator_shadow_mode_no_rewrite.py`
- `backend/tests/test_world_backstop_and_trace_fields.py`
- `backend/tests/test_world_belief_background_prompting.py`
- `backend/tests/test_world_belief_v2_normalization.py`
- `backend/tests/test_world_extractor_v4_multisignal_context_contradictions.py`
- `backend/tests/test_world_judge_always_on.py`
- `backend/tests/test_world_judge_contracts.py`
- `backend/tests/test_world_latency_telemetry.py`
- `backend/tests/test_world_llm_no_regex.py`
- `backend/tests/test_world_state_shape.py`
- `backend/tests/test_world_tradeoff_and_belief_fallback.py`

---

## Lista exacta de símbolos/bloques eliminados dentro de archivos
- Prompts runtime legacy eliminados del bundle (`backend/prompts.py`):
  - `WORLD_JUDGE_V2_*`
  - `PLANNER_V2_*`
- Judge legacy internals eliminados de `backend/negotiation/nodes/world_node.py`:
  - normalizers/guardrails/evidence helpers.
- Modelos planner legacy eliminados de `backend/negotiation/elementos/strategy_definitions.py`:
  - stack `PlannerV2*` step-driven.
- Estado/telemetría legacy como motor eliminado:
  - `backend/negotiation/schemas.py` (campos legacy de plan rígido)
  - `backend/negotiation/progress_updater.py` (motor de ledger/counters legacy)
- Executor step-driven eliminado:
  - `backend/negotiation/nodes/executor_node.py` (enforcement por instrucciones rígidas)
  - `backend/negotiation/executor/render_executor.py` (dependencia de payload rígido legacy)

---

## Evidencia de smoke (estado final solicitado)
Ver: `docs/cleanup_audit/smoke_semantic_turns.txt`.
Incluye:
- `progress_state.semantic_ledger`
- `state.planner_semantic_output`
- `executor_output.response_text`
