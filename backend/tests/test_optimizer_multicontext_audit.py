from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import app
from sessions.state import SESSIONS, SessionState, get_session_state
from sessions.surface_scope import SESSION_SURFACE_WORLD_STATE_KEY

TARGET_CONTEXT = 'validacion_multicontexto'
BASELINE_CONTEXT = 'baseline_current'


def fake_execute_turn_with_contract(*, state: SessionState, user_message: str, config: Any, contract: Any):
    memory_key = config.memory_key
    traces = state.world_state.setdefault(f'{memory_key}_traces', [])
    idx = len(traces) + 1
    turn_id = f'turn::{state.user_id}::{state.session_id}::{idx}'
    trace = {
        'turn_id': turn_id,
        'final_status': 'ok',
        'final_reply_text': f'stub::{user_message}',
        'user_turn': {'raw_text': user_message},
        'context_meta': state.world_state.get('negotiation_context', {}),
        'conversation_id_before': f'conv::{state.user_id}::{state.session_id}',
        'conversation_id_after': f'conv::{state.user_id}::{state.session_id}',
        'logs': [],
        'nodes': {},
    }
    traces.append(trace)
    return f'stub::{user_message}', state, {
        'entry_contract': {
            'entry_surface': getattr(contract, 'entry_surface', None),
            'entrypoint': getattr(contract, 'entrypoint', None),
            'overrides_applied': getattr(contract, 'overrides_applied', False),
            'optimizer_wrapper_used': getattr(contract, 'optimizer_wrapper_used', False),
            'new_conversation': getattr(contract, 'new_conversation', False),
            'clone_used': getattr(contract, 'clone_used', False),
            'config_snapshot': {
                'memory_key': config.memory_key,
                'thread_mode_default': getattr(config.thread_mode_default, 'value', str(config.thread_mode_default)),
                'model_memory': config.model_memory,
                'model_phase_classifier': config.model_phase_classifier,
                'model_planner': config.model_planner,
                'model_executor': config.model_executor,
                'max_recent_messages': config.max_recent_messages,
                'max_executor_recent_turns': config.max_executor_recent_turns,
            },
        },
        'trace_count': len(traces),
        'latest_turn_id': turn_id,
    }


class OptimizerIsolationAndContextTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        self.client = TestClient(app)

    def _patch_optimizer_runtime(self):
        return patch('negociacion.optimizador.services.execute_turn_with_contract', side_effect=fake_execute_turn_with_contract)

    def _patch_interfaz_runtime(self):
        return patch('interfaz_usuario.services.execute_turn_with_contract', side_effect=fake_execute_turn_with_contract)

    def test_optimizer_contexts_endpoint_lists_official_contexts(self) -> None:
        response = self.client.get('/api/optimizador/contexts')
        self.assertEqual(response.status_code, 200)
        context_ids = {item['context_id'] for item in response.json()['items']}
        self.assertIn(BASELINE_CONTEXT, context_ids)
        self.assertIn(TARGET_CONTEXT, context_ids)

    def test_optimizer_bootstrap_binds_selected_context_and_surface(self) -> None:
        response = self.client.post('/api/optimizador/sessions/bootstrap', json={'user_id': 'u_opt', 'session_id': 's_opt', 'context_id': TARGET_CONTEXT})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['base_context']['context_id'], TARGET_CONTEXT)
        state = get_session_state(user_id='u_opt', session_id='s_opt')
        self.assertEqual(state.world_state['negotiation_context']['context_id'], TARGET_CONTEXT)
        self.assertEqual(state.world_state[SESSION_SURFACE_WORLD_STATE_KEY], 'optimizador')

    def test_optimizer_sandbox_turn_uses_selected_context(self) -> None:
        self.client.post('/api/optimizador/sessions/bootstrap', json={'user_id': 'u_opt', 'session_id': 's_opt', 'context_id': TARGET_CONTEXT})
        captured: dict[str, Any] = {}

        def capture_execute(*, state: SessionState, user_message: str, config: Any, contract: Any):
            captured['prompts_dir'] = config.prompts_dir
            return fake_execute_turn_with_contract(state=state, user_message=user_message, config=config, contract=contract)

        with patch('negociacion.optimizador.services.execute_turn_with_contract', side_effect=capture_execute), patch(
            'negociacion.optimizador.services.experiments_bridge.resolve_entries', return_value=[]
        ), patch(
            'negociacion.optimizador.services.experiments_bridge.apply_overrides', side_effect=lambda config, entries, context_id=None: (config, None)
        ), patch(
            'negociacion.optimizador.services.experiments_bridge.describe_effective_overrides', return_value={'prompt': {}, 'config': {}, 'contextual': {}}
        ), patch(
            'negociacion.optimizador.services.experiments_bridge.get_state', return_value={'mode': 'mirror', 'workspace_version': 1}
        ):
            response = self.client.post('/api/optimizador/sandbox/turn', json={
                'optimizer_session_id': 'audit',
                'user_id': 'u_opt',
                'session_id': 's_opt',
                'message': 'hola',
                'conversation_id': None,
                'scope_turn_id': None,
                'repeat_from_turn_id': None,
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn(TARGET_CONTEXT, str(captured['prompts_dir']))
        turns = self.client.get('/api/optimizador/sessions/u_opt/s_opt/turns').json()['items']
        self.assertEqual(turns[-1]['context_id'], TARGET_CONTEXT)

    def test_optimizer_prompts_api_reflects_active_session_context(self) -> None:
        self.client.post('/api/optimizador/sessions/bootstrap', json={'user_id': 'u_base', 'session_id': 's_base', 'context_id': BASELINE_CONTEXT})
        self.client.post('/api/optimizador/sessions/bootstrap', json={'user_id': 'u_alt', 'session_id': 's_alt', 'context_id': TARGET_CONTEXT})

        baseline = self.client.get('/api/optimizador/prompts', params={'user_id': 'u_base', 'session_id': 's_base'})
        alternate = self.client.get('/api/optimizador/prompts', params={'user_id': 'u_alt', 'session_id': 's_alt'})

        self.assertEqual(baseline.status_code, 200)
        self.assertEqual(alternate.status_code, 200)
        baseline_planner = next(item for item in baseline.json()['items'] if item['node'] == 'planner')
        alternate_planner = next(item for item in alternate.json()['items'] if item['node'] == 'planner')
        self.assertIn('/baseline_current/prompts/', baseline_planner['file'])
        self.assertIn(f'/{TARGET_CONTEXT}/prompts/', alternate_planner['file'])

    def test_optimizer_does_not_list_interfaz_usuario_sessions(self) -> None:
        with self._patch_interfaz_runtime():
            self.client.post('/api/interfaz_usuario/negociacion/turn', json={'user_id': 'iu_user', 'session_id': 'iu_session', 'message': 'hola', 'new_conversation': False})
        items = self.client.get('/api/optimizador/sessions').json()['items']
        session_keys = {item['session_key'] for item in items}
        self.assertNotIn('iu_user::iu_session', session_keys)

    def test_optimizer_cannot_read_interfaz_usuario_turns(self) -> None:
        with self._patch_interfaz_runtime():
            self.client.post('/api/interfaz_usuario/negociacion/turn', json={'user_id': 'iu_user', 'session_id': 'iu_session', 'message': 'hola', 'new_conversation': False})
        state = get_session_state(user_id='iu_user', session_id='iu_session')
        turn_id = state.world_state['negotiation_canonical_traces'][0]['turn_id']
        response = self.client.get(f'/api/optimizador/turns/{turn_id}')
        self.assertEqual(response.status_code, 404)

    def test_optimizer_cannot_clone_interfaz_usuario_sessions(self) -> None:
        with self._patch_interfaz_runtime():
            self.client.post('/api/interfaz_usuario/negociacion/turn', json={'user_id': 'iu_user', 'session_id': 'iu_session', 'message': 'hola', 'new_conversation': False})
        response = self.client.post('/api/optimizador/sandbox/clone', json={
            'optimizer_session_id': 'audit',
            'source_user_id': 'iu_user',
            'source_session_id': 'iu_session',
            'source_conversation_id': None,
        })
        self.assertEqual(response.status_code, 400)

    def test_optimizer_and_interfaz_conflict_if_same_key_is_reused(self) -> None:
        self.client.post('/api/optimizador/sessions/bootstrap', json={'user_id': 'shared', 'session_id': 'same', 'context_id': BASELINE_CONTEXT})
        response = self.client.post('/api/interfaz_usuario/sessions/bootstrap', json={'user_id': 'shared', 'session_id': 'same', 'context_id': BASELINE_CONTEXT})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail']['error'], 'session_surface_conflict')

    def test_optimizer_frontend_has_context_selector_and_context_aware_prompts_call(self) -> None:
        js = Path('backend/avatar_app/optimizador/app.js').read_text(encoding='utf-8')
        self.assertIn('contextSelector', js)
        self.assertIn('/contexts', js)
        self.assertIn('/prompts?user_id=', js)
        self.assertIn('Contexto activo', js)


if __name__ == '__main__':
    unittest.main()
