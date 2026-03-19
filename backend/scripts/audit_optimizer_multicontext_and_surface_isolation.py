from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from api.app import app
from sessions.state import SESSIONS, SessionState, get_session_state
from sessions.surface_scope import SESSION_SURFACE_WORLD_STATE_KEY

REPORT_PATH = Path('docs/optimizer_audit_report.json')
TARGET_CONTEXT = 'validacion_multicontexto'
BASELINE_CONTEXT = 'baseline_current'


def _fake_execute_turn_with_contract(*, state: SessionState, user_message: str, config: Any, contract: Any):
    memory_key = config.memory_key
    traces_key = f'{memory_key}_traces'
    traces = state.world_state.setdefault(traces_key, [])
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


def run_audit() -> dict[str, Any]:
    SESSIONS.clear()
    client = TestClient(app)

    optimizer_js = (ROOT / 'avatar_app' / 'optimizador' / 'app.js').read_text(encoding='utf-8')
    contexts_response = client.get('/api/optimizador/contexts')

    optimizer_boot = client.post('/api/optimizador/sessions/bootstrap', json={'user_id': 'u_opt', 'session_id': 's_opt', 'context_id': TARGET_CONTEXT})
    optimizer_state = get_session_state(user_id='u_opt', session_id='s_opt')

    with patch('negociacion.optimizador.services.execute_turn_with_contract', side_effect=_fake_execute_turn_with_contract), patch(
        'negociacion.optimizador.services.experiments_bridge.resolve_entries', return_value=[]
    ), patch(
        'negociacion.optimizador.services.experiments_bridge.apply_overrides', side_effect=lambda config, entries, context_id=None: (config, None)
    ), patch(
        'negociacion.optimizador.services.experiments_bridge.describe_effective_overrides', return_value={'prompt': {}, 'config': {}, 'contextual': {}}
    ), patch(
        'negociacion.optimizador.services.experiments_bridge.get_state', return_value={'mode': 'mirror', 'workspace_version': 1}
    ):
        turn_response = client.post('/api/optimizador/sandbox/turn', json={
            'optimizer_session_id': 'audit',
            'user_id': 'u_opt',
            'session_id': 's_opt',
            'message': 'hola contexto',
            'conversation_id': None,
            'scope_turn_id': None,
            'repeat_from_turn_id': None,
        })

    prompts_response = client.get('/api/optimizador/prompts', params={'user_id': 'u_opt', 'session_id': 's_opt'})
    turns_response = client.get('/api/optimizador/sessions/u_opt/s_opt/turns')

    with patch('interfaz_usuario.services.execute_turn_with_contract', side_effect=_fake_execute_turn_with_contract):
        iu_turn = client.post('/api/interfaz_usuario/negociacion/turn', json={
            'user_id': 'iu_user', 'session_id': 'iu_session', 'message': 'hola iu', 'new_conversation': False,
        })

    sessions_response = client.get('/api/optimizador/sessions')
    iu_state = get_session_state(user_id='iu_user', session_id='iu_session')
    iu_turn_id = iu_state.world_state['negotiation_canonical_traces'][0]['turn_id']
    turn_visibility = client.get(f'/api/optimizador/turns/{iu_turn_id}')
    clone_visibility = client.post('/api/optimizador/sandbox/clone', json={
        'optimizer_session_id': 'audit',
        'source_user_id': 'iu_user',
        'source_session_id': 'iu_session',
        'source_conversation_id': None,
    })
    same_key_conflict = client.post('/api/interfaz_usuario/sessions/bootstrap', json={'user_id': 'u_opt', 'session_id': 's_opt', 'context_id': TARGET_CONTEXT})

    report = {
        'ui': {
            'has_context_selector': 'contextSelector' in optimizer_js,
            'loads_contexts_endpoint': '/contexts' in optimizer_js,
            'prompts_follow_active_session': '/prompts?user_id=' in optimizer_js,
            'shows_active_context_label': 'Contexto activo' in optimizer_js,
        },
        'contexts_endpoint': contexts_response.json(),
        'optimizer_bootstrap': optimizer_boot.json(),
        'optimizer_surface_binding': optimizer_state.world_state.get(SESSION_SURFACE_WORLD_STATE_KEY),
        'runtime': {
            'sandbox_turn_status': turn_response.status_code,
            'turns': turns_response.json()['items'],
        },
        'prompts': {
            'status_code': prompts_response.status_code,
            'items': prompts_response.json()['items'],
        },
        'interfaz_isolation': {
            'interfaz_turn_status': iu_turn.status_code,
            'optimizer_sessions': sessions_response.json()['items'],
            'optimizer_turn_lookup_status': turn_visibility.status_code,
            'optimizer_clone_status': clone_visibility.status_code,
            'same_key_conflict_status': same_key_conflict.status_code,
            'same_key_conflict_detail': same_key_conflict.json(),
        },
    }
    return report


def main() -> None:
    report = run_audit()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
