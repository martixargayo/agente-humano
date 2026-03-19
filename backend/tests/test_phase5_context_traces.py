from __future__ import annotations

import unittest
from unittest.mock import patch

from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from negociacion.optimizador import services as optimizer_services
from negociacion.optimizador import trace_reader
from negociacion.traces.models import TurnTrace
from sessions.state import SESSIONS, get_session_state


class Phase5ContextTracesTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()

    def test_baseline_turn_persists_context_metadata_in_trace(self) -> None:
        state = get_session_state(user_id='u_trace', session_id='s_trace')
        from interfaz_usuario.services import ensure_session

        ensure_session(user_id='u_trace', session_id='s_trace')
        config = build_negotiation_pipeline_config()

        def fake_turn(current_state, user_message, current_config):
            current_state.world_state[f'{current_config.memory_key}_traces'] = [{'turn_id': 'turn-1'}]
            current_state.world_state[current_config.memory_key] = {'openai_thread': {'conversation_id': 'conv-1', 'previous_response_id': 'resp-1'}}
            return 'ok', current_state

        with patch('negociacion.orchestration.turn_contract.run_negotiation_cognitive_turn', side_effect=fake_turn):
            reply, updated_state, meta = execute_turn_with_contract(
                state=state,
                user_message='hola',
                config=config,
                contract=TurnEntryContract(
                    entry_surface='interfaz_usuario',
                    entrypoint='/api/interfaz_usuario/negociacion/turn',
                    overrides_applied=False,
                    optimizer_wrapper_used=False,
                ),
            )

        trace = updated_state.world_state[f'{config.memory_key}_traces'][-1]
        self.assertEqual(reply, 'ok')
        self.assertEqual(trace['context_meta']['flow_id'], 'negociacion')
        self.assertEqual(trace['context_meta']['context_id'], 'baseline_current')
        self.assertEqual(trace['context_meta']['context_version'], '1.0.0')
        self.assertEqual(trace['_entry_contract']['context_meta']['context_scope'], 'official')
        self.assertEqual(meta['entry_contract']['context_meta']['context_id'], 'baseline_current')

    def test_entry_contract_marks_official_with_overrides_without_changing_trace_shape(self) -> None:
        state = get_session_state(user_id='u_override', session_id='s_override')
        from interfaz_usuario.services import ensure_session

        ensure_session(user_id='u_override', session_id='s_override')
        config = build_negotiation_pipeline_config()

        def fake_turn(current_state, user_message, current_config):
            current_state.world_state[f'{current_config.memory_key}_traces'] = [{'turn_id': 'turn-override'}]
            current_state.world_state[current_config.memory_key] = {'openai_thread': {}}
            return 'reply-override', current_state

        with patch('negociacion.orchestration.turn_contract.run_negotiation_cognitive_turn', side_effect=fake_turn):
            _, updated_state, meta = execute_turn_with_contract(
                state=state,
                user_message='hola',
                config=config,
                contract=TurnEntryContract(
                    entry_surface='optimizador',
                    entrypoint='/api/optimizador/sandbox/turn',
                    overrides_applied=True,
                    optimizer_wrapper_used=True,
                ),
            )

        trace = updated_state.world_state[f'{config.memory_key}_traces'][-1]
        self.assertEqual(trace['context_meta']['context_scope'], 'official_with_overrides')
        self.assertEqual(trace['_entry_contract']['context_meta']['context_scope'], 'official_with_overrides')
        self.assertEqual(meta['entry_contract']['context_meta']['context_scope'], 'official_with_overrides')
        self.assertEqual(set(meta.keys()), {
            'trace_count',
            'conversation_id_before',
            'conversation_id_after',
            'previous_response_id_before',
            'previous_response_id_after',
            'latest_turn_id',
            'entry_contract',
        })

    def test_legacy_turn_trace_remains_parseable_without_context_meta(self) -> None:
        legacy_payload = {
            'trace_version': 'turn_trace.rich.v1',
            'turn_id': 'legacy-1',
            'timestamp_utc': '2026-03-19T00:00:00+00:00',
            'turn_started_at': '2026-03-19T00:00:00+00:00',
            'turn_finished_at': '2026-03-19T00:00:01+00:00',
            'total_latency_ms': 1000,
            'session_id': 's',
            'user_id': 'u',
            'avatar_id': None,
            'thread_mode': 'conversation',
            'conversation_id_before': None,
            'conversation_id_after': None,
            'previous_response_id_before': None,
            'previous_response_id_after': None,
            'user_turn': {'raw_text': 'hola', 'normalized_text': 'hola', 'modality': 'text', 'language': 'es', 'timestamp_iso': '2026-03-19T00:00:00+00:00'},
            'final_reply_text': 'hola',
            'final_reply_excerpt': 'hola',
            'final_status': 'clarify',
            'assistant_turn_emitted': True,
            'executor_reply_text_before_guardrail': None,
            'executor_status_before_guardrail': None,
            'executor_reply_changed_by_guardrail': False,
            'final_output_source': 'executor_post_guardrail',
            'guardrails_triggered': False,
            'guardrail_reasons': [],
            'guardrail_rewrite_applied': False,
            'guardrail_status_before': 'clarify',
            'guardrail_status_after': 'clarify',
            'input_guardrail_decision': 'allow',
            'input_guardrail_reasons': [],
            'input_guardrail_triggered': False,
            'input_moderation_used': False,
            'input_moderation_flags': [],
            'output_guardrail_decision': 'allow',
            'output_guardrail_reasons': [],
            'output_guardrail_triggered': False,
            'output_guardrail_rewrite_applied': False,
            'output_guardrail_enforcement_mode': 'observe_only',
            'output_guardrail_enforcement_action': 'none',
            'output_guardrail_observed_not_applied_rules': [],
            'output_guardrail_enforced_rules': [],
            'output_guardrail_output_changed': False,
            'output_guardrail_status_before': 'clarify',
            'output_guardrail_status_after': 'clarify',
            'output_moderation_used': False,
            'output_moderation_flags': [],
            'model_memory': 'm1',
            'model_phase_classifier': 'm2',
            'model_planner': 'm3',
            'model_executor': 'm4',
            'prompt_version_memory': 'p1',
            'prompt_version_phase_classifier': 'p2',
            'prompt_version_planner': 'p3',
            'prompt_version_executor': 'p4',
            'schema_version_memory': 's1',
            'schema_version_phase_classifier': 's2',
            'schema_version_planner': 's3',
            'schema_version_executor': 's4',
            'sdk_compatibility': {'installed_version': '1', 'minimum_version': '1', 'status': 'compatible', 'details': 'ok'},
            'grades': {'planner_coherence': 'pending', 'executor_naturalness': 'pending', 'planner_executor_agreement': True, 'safety_compliance': True},
            'logs': [],
            'nodes': {},
        }

        parsed = TurnTrace.model_validate(legacy_payload)
        self.assertIsNone(parsed.context_meta)

    def test_optimizer_trace_keeps_base_context_metadata(self) -> None:
        state = get_session_state(user_id='u_opt_trace', session_id='s_opt_trace')
        from interfaz_usuario.services import ensure_session

        ensure_session(user_id='u_opt_trace', session_id='s_opt_trace')
        state.world_state['optimizador_sandbox_meta'] = {'clone_strategy': 'new_conversation_clean_start'}
        state.world_state['negotiation_canonical_traces'] = [{'turn_id': 'turn-opt', 'context_meta': {'flow_id': 'negociacion', 'context_id': 'baseline_current', 'context_version': '1.0.0'}}]

        cfg = type('Cfg', (), {'memory_key': 'negotiation_canonical'})()
        with patch('negociacion.optimizador.services.build_negotiation_pipeline_config', return_value=cfg), patch(
            'negociacion.optimizador.services.experiments_bridge.resolve_entries', return_value=[{'scope': 'conversation', 'category': 'config', 'key': 'x', 'value': 1}],
        ), patch('negociacion.optimizador.services.experiments_bridge.apply_overrides', return_value=(cfg, None)), patch(
            'negociacion.optimizador.services.execute_turn_with_contract',
            return_value=('reply', state, {'entry_contract': {'entry_surface': 'optimizador'}, 'trace_count': 1}),
        ), patch('negociacion.optimizador.services.experiments_bridge.describe_effective_overrides', return_value={'prompt': {}, 'config': {}, 'contextual': {}}), patch(
            'negociacion.optimizador.services.experiments_bridge.get_state', return_value={'mode': 'mirror', 'workspace_version': 1}
        ), patch('negociacion.optimizador.services.list_turns', return_value=[{'turn_id': 'turn-opt'}]), patch(
            'negociacion.optimizador.services.derive_turn_title', return_value='Turno 1 · v1'
        ):
            result = optimizer_services.run_sandbox_turn(
                optimizer_session_id='opt-1',
                user_id='u_opt_trace',
                session_id='s_opt_trace',
                message='hola',
                conversation_id=None,
                scope_turn_id=None,
                repeat_from_turn_id=None,
            )

        optimizer_meta = state.world_state['negotiation_canonical_traces'][-1]['_optimizador']
        self.assertEqual(optimizer_meta['base_context']['context_id'], 'baseline_current')
        self.assertTrue(optimizer_meta['base_context']['official_context_used'])
        self.assertEqual(optimizer_meta['base_context']['context_scope'], 'official_with_overrides')
        self.assertIsNotNone(result['turn'])

    def test_trace_reader_exposes_context_summary_when_present(self) -> None:
        state = get_session_state(user_id='u_reader', session_id='s_reader')
        state.world_state['negotiation_canonical_traces'] = [
            {
                'turn_id': 'turn-reader',
                'turn_started_at': '2026-03-19T00:00:00+00:00',
                'final_status': 'clarify',
                'total_latency_ms': 10,
                'guardrails_triggered': False,
                'logs': [],
                'context_meta': {'flow_id': 'negociacion', 'context_id': 'baseline_current', 'context_version': '1.0.0'},
            }
        ]

        turns = trace_reader.list_turns(user_id='u_reader', session_id='s_reader')
        self.assertEqual(turns[0]['flow_id'], 'negociacion')
        self.assertEqual(turns[0]['context_id'], 'baseline_current')
        self.assertEqual(turns[0]['context_version'], '1.0.0')

    def test_session_and_trace_do_not_diverge_for_baseline(self) -> None:
        state = get_session_state(user_id='u_sync', session_id='s_sync')
        from interfaz_usuario.services import ensure_session

        ensure_session(user_id='u_sync', session_id='s_sync')
        config = build_negotiation_pipeline_config()

        def fake_turn(current_state, user_message, current_config):
            current_state.world_state[f'{current_config.memory_key}_traces'] = [{'turn_id': 'turn-sync'}]
            current_state.world_state[current_config.memory_key] = {'openai_thread': {}}
            return 'reply', current_state

        with patch('negociacion.orchestration.turn_contract.run_negotiation_cognitive_turn', side_effect=fake_turn):
            _, updated_state, _ = execute_turn_with_contract(
                state=state,
                user_message='hola',
                config=config,
                contract=TurnEntryContract(
                    entry_surface='interfaz_usuario',
                    entrypoint='/api/interfaz_usuario/negociacion/turn',
                    overrides_applied=False,
                    optimizer_wrapper_used=False,
                ),
            )

        trace = updated_state.world_state[f'{config.memory_key}_traces'][-1]
        session_context = updated_state.world_state['negotiation_context']
        self.assertEqual(trace['context_meta']['context_id'], session_context['context_id'])
        self.assertEqual(trace['context_meta']['context_version'], session_context['context_version'])


if __name__ == '__main__':
    unittest.main()
