from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from negociacion.contexts import NEGOTIATION_CONTEXT_WORLD_STATE_KEY
from negociacion.optimizador import services as optimizer_services
from negociacion.optimizador import trace_reader
from sessions.state import SESSIONS, get_session_state


class Phase7OptimizerContextAwareTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()

    def test_optimizer_bootstrap_without_context_id_binds_default_baseline_and_exposes_base_context(self) -> None:
        payload = optimizer_services.ensure_session(user_id='u_opt', session_id='s_opt')

        state = get_session_state(user_id='u_opt', session_id='s_opt')
        self.assertEqual(
            state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
            {
                'flow_id': 'negociacion',
                'context_id': 'baseline_current',
                'context_version': '1.0.0',
            },
        )
        self.assertEqual(payload['base_context']['context_id'], 'baseline_current')
        self.assertEqual(payload['base_context']['context_version'], '1.0.0')

    def test_optimizer_bootstrap_with_explicit_baseline_context_keeps_same_base_context(self) -> None:
        payload = optimizer_services.ensure_session(user_id='u_opt_explicit', session_id='s_opt_explicit', context_id='baseline_current')

        state = get_session_state(user_id='u_opt_explicit', session_id='s_opt_explicit')
        self.assertEqual(state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]['context_id'], 'baseline_current')
        self.assertEqual(payload['base_context'], {
            'flow_id': 'negociacion',
            'context_id': 'baseline_current',
            'context_version': '1.0.0',
        })

    def test_optimizer_clone_inherits_bound_source_context_into_sandbox_meta(self) -> None:
        optimizer_services.ensure_session(user_id='u_clone', session_id='s_source')

        created = optimizer_services.duplicate_sandbox_session(
            optimizer_session_id='opt-1',
            source_user_id='u_clone',
            source_session_id='s_source',
            source_conversation_id='conv-1',
        )

        sandbox_state = get_session_state(user_id='u_clone', session_id=created['session_id'])
        self.assertEqual(
            sandbox_state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
            {
                'flow_id': 'negociacion',
                'context_id': 'baseline_current',
                'context_version': '1.0.0',
            },
        )
        self.assertEqual(created['sandbox_meta']['base_context']['context_id'], 'baseline_current')
        self.assertEqual(created['base_context']['context_version'], '1.0.0')

    def test_optimizer_new_conversation_inherits_context_without_silent_mix(self) -> None:
        optimizer_services.ensure_session(user_id='u_new', session_id='s_base')

        created = optimizer_services.new_conversation_session(
            optimizer_session_id='opt-2',
            user_id='u_new',
            session_id='s_base',
        )

        derived_state = get_session_state(user_id='u_new', session_id=created['session_id'])
        self.assertEqual(
            derived_state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
            {
                'flow_id': 'negociacion',
                'context_id': 'baseline_current',
                'context_version': '1.0.0',
            },
        )
        self.assertEqual(created['sandbox_meta']['base_context']['context_id'], 'baseline_current')
        self.assertEqual(created['base_context']['context_id'], 'baseline_current')

    def test_optimizer_clone_rejects_conflicting_requested_context(self) -> None:
        optimizer_services.ensure_session(user_id='u_conflict', session_id='s_conflict')

        with self.assertRaises(HTTPException) as ctx:
            optimizer_services.duplicate_sandbox_session(
                optimizer_session_id='opt-3',
                source_user_id='u_conflict',
                source_session_id='s_conflict',
                source_conversation_id=None,
                context_id='otro_contexto',
            )

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail['error'], 'optimizer_context_conflict')

    def test_optimizer_new_conversation_rejects_conflicting_requested_context(self) -> None:
        optimizer_services.ensure_session(user_id='u_conflict_new', session_id='s_conflict_new')

        with self.assertRaises(HTTPException) as ctx:
            optimizer_services.new_conversation_session(
                optimizer_session_id='opt-4',
                user_id='u_conflict_new',
                session_id='s_conflict_new',
                context_id='otro_contexto',
            )

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail['error'], 'optimizer_context_conflict')

    def test_run_sandbox_turn_persists_visible_base_context_without_overrides(self) -> None:
        optimizer_services.ensure_session(user_id='u_turn', session_id='s_turn')
        state = get_session_state(user_id='u_turn', session_id='s_turn')
        state.world_state['optimizador_sandbox_meta'] = {'clone_strategy': 'new_conversation_clean_start'}
        cfg = type('Cfg', (), {'memory_key': 'negotiation_canonical'})()
        state.world_state['negotiation_canonical_traces'] = [
            {
                'turn_id': 'turn-before',
                'context_meta': {'flow_id': 'negociacion', 'context_id': 'baseline_current', 'context_version': '1.0.0'},
            }
        ]

        with patch('negociacion.optimizador.services.build_negotiation_pipeline_config', return_value=cfg), patch(
            'negociacion.optimizador.services.experiments_bridge.resolve_entries', return_value=[]
        ), patch('negociacion.optimizador.services.experiments_bridge.apply_overrides', return_value=(cfg, None)), patch(
            'negociacion.optimizador.services.execute_turn_with_contract',
            return_value=('reply', state, {'entry_contract': {'entry_surface': 'optimizador'}, 'trace_count': 1}),
        ), patch('negociacion.optimizador.services.experiments_bridge.describe_effective_overrides', return_value={'prompt': {}, 'config': {}, 'contextual': {}}), patch(
            'negociacion.optimizador.services.experiments_bridge.get_state', return_value={'mode': 'mirror', 'workspace_version': 1}
        ), patch('negociacion.optimizador.services.list_turns', return_value=[{'turn_id': 'turn-before'}]), patch(
            'negociacion.optimizador.services.derive_turn_title', return_value='Turno 1 · v1'
        ):
            result = optimizer_services.run_sandbox_turn(
                optimizer_session_id='opt-turn',
                user_id='u_turn',
                session_id='s_turn',
                message='hola',
                conversation_id=None,
                scope_turn_id=None,
                repeat_from_turn_id=None,
            )

        optimizer_meta = state.world_state['negotiation_canonical_traces'][-1]['_optimizador']
        self.assertEqual(result['reply'], 'reply')
        self.assertEqual(optimizer_meta['base_context']['context_id'], 'baseline_current')
        self.assertEqual(optimizer_meta['base_context']['context_version'], '1.0.0')
        self.assertTrue(optimizer_meta['base_context']['official_context_used'])
        self.assertEqual(optimizer_meta['base_context']['context_scope'], 'official')

    def test_run_sandbox_turn_keeps_base_context_visible_when_overrides_exist(self) -> None:
        optimizer_services.ensure_session(user_id='u_override', session_id='s_override')
        state = get_session_state(user_id='u_override', session_id='s_override')
        cfg = type('Cfg', (), {'memory_key': 'negotiation_canonical'})()
        state.world_state['optimizador_sandbox_meta'] = {'clone_strategy': 'full_session_with_preferred_conversation'}
        state.world_state['negotiation_canonical_traces'] = [
            {
                'turn_id': 'turn-override',
                'context_meta': {'flow_id': 'negociacion', 'context_id': 'baseline_current', 'context_version': '1.0.0'},
            }
        ]
        effective_overrides = {'prompt': {'planner_prompt': 'override'}, 'config': {}, 'contextual': {}}

        with patch('negociacion.optimizador.services.build_negotiation_pipeline_config', return_value=cfg), patch(
            'negociacion.optimizador.services.experiments_bridge.resolve_entries',
            return_value=[{'scope': 'this_optimizer_session', 'category': 'prompt', 'key': 'planner_prompt', 'value': 'override'}],
        ), patch('negociacion.optimizador.services.experiments_bridge.apply_overrides', return_value=(cfg, None)), patch(
            'negociacion.optimizador.services.execute_turn_with_contract',
            return_value=('reply-override', state, {'entry_contract': {'entry_surface': 'optimizador'}, 'trace_count': 1}),
        ), patch('negociacion.optimizador.services.experiments_bridge.describe_effective_overrides', return_value=effective_overrides), patch(
            'negociacion.optimizador.services.experiments_bridge.get_state', return_value={'mode': 'sandbox', 'workspace_version': 3}
        ), patch('negociacion.optimizador.services.list_turns', return_value=[{'turn_id': 'turn-override'}]), patch(
            'negociacion.optimizador.services.derive_turn_title', return_value='Turno 2 · v1'
        ):
            result = optimizer_services.run_sandbox_turn(
                optimizer_session_id='opt-override',
                user_id='u_override',
                session_id='s_override',
                message='hola',
                conversation_id='conv-override',
                scope_turn_id=None,
                repeat_from_turn_id=None,
            )

        optimizer_meta = state.world_state['negotiation_canonical_traces'][-1]['_optimizador']
        self.assertEqual(result['effective_overrides'], effective_overrides)
        self.assertTrue(optimizer_meta['used_overrides'])
        self.assertEqual(optimizer_meta['base_context']['context_id'], 'baseline_current')
        self.assertEqual(optimizer_meta['base_context']['context_scope'], 'official_with_overrides')
        self.assertTrue(optimizer_meta['base_context']['official_context_used'])

    def test_trace_reader_reports_optimizer_base_context_diagnostically(self) -> None:
        optimizer_services.ensure_session(user_id='u_reader', session_id='s_reader')
        state = get_session_state(user_id='u_reader', session_id='s_reader')
        state.world_state['negotiation_canonical_traces'] = [
            {
                'turn_id': 'turn-reader',
                'turn_started_at': '2026-03-19T00:00:00+00:00',
                'final_status': 'clarify',
                'total_latency_ms': 12,
                'guardrails_triggered': False,
                'logs': [],
                'context_meta': {'flow_id': 'negociacion', 'context_id': 'baseline_current', 'context_version': '1.0.0'},
                '_optimizador': {
                    'base_context': {
                        'flow_id': 'negociacion',
                        'context_id': 'baseline_current',
                        'context_version': '1.0.0',
                        'context_scope': 'official_with_overrides',
                        'official_context_used': True,
                    },
                    'applied_overrides': {'prompt': {'planner_prompt': 'override'}, 'config': {}, 'contextual': {}},
                    'versioning': {'base_turn_id': 'turn-reader', 'version': 2},
                },
            }
        ]

        turns = trace_reader.list_turns(user_id='u_reader', session_id='s_reader')
        self.assertEqual(turns[0]['context_id'], 'baseline_current')
        self.assertEqual(turns[0]['context_scope'], 'official_with_overrides')
        self.assertTrue(turns[0]['official_context_used'])
        self.assertEqual(turns[0]['base_context']['context_version'], '1.0.0')
        self.assertTrue(turns[0]['has_override'])
        self.assertEqual(turns[0]['version'], 2)

    def test_optimizer_baseline_compatibility_remains_when_no_context_id_is_provided(self) -> None:
        payload = optimizer_services.ensure_session(user_id='u_compat', session_id='s_compat')
        listed = optimizer_services.list_sessions()

        self.assertEqual(payload['base_context']['context_id'], 'baseline_current')
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]['base_context']['context_id'], 'baseline_current')
        self.assertFalse(listed[0]['is_sandbox'])


if __name__ == '__main__':
    unittest.main()
