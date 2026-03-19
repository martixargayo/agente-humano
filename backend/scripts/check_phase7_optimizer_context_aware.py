from __future__ import annotations

from unittest.mock import patch

from negociacion.optimizador import services as optimizer_services
from sessions.state import SESSIONS, get_session_state


class _Cfg:
    memory_key = 'negotiation_canonical'


def main() -> None:
    SESSIONS.clear()

    print('[optimizer_bootstrap_default]')
    default_payload = optimizer_services.ensure_session(user_id='u_phase7', session_id='s_phase7')
    print(default_payload)

    print('\n[optimizer_bootstrap_explicit_baseline]')
    explicit_payload = optimizer_services.ensure_session(
        user_id='u_phase7_explicit',
        session_id='s_phase7_explicit',
        context_id='baseline_current',
    )
    print(explicit_payload)

    print('\n[sandbox_clone_inherits_context]')
    cloned = optimizer_services.duplicate_sandbox_session(
        optimizer_session_id='opt-phase7',
        source_user_id='u_phase7',
        source_session_id='s_phase7',
        source_conversation_id='conv-phase7',
    )
    print(cloned)

    print('\n[sandbox_new_conversation_inherits_context]')
    new_conv = optimizer_services.new_conversation_session(
        optimizer_session_id='opt-phase7',
        user_id='u_phase7',
        session_id='s_phase7',
    )
    print(new_conv)

    print('\n[explicit_context_conflict]')
    try:
        optimizer_services.new_conversation_session(
            optimizer_session_id='opt-phase7',
            user_id='u_phase7',
            session_id='s_phase7',
            context_id='otro_contexto',
        )
    except Exception as exc:  # script diagnóstico manual
        print(getattr(exc, 'detail', str(exc)))

    state = get_session_state(user_id='u_phase7', session_id='s_phase7')
    state.world_state['optimizador_sandbox_meta'] = {'clone_strategy': 'full_session_with_preferred_conversation'}
    state.world_state['negotiation_canonical_traces'] = [
        {
            'turn_id': 'turn-phase7',
            'context_meta': {'flow_id': 'negociacion', 'context_id': 'baseline_current', 'context_version': '1.0.0'},
        }
    ]

    print('\n[sandbox_turn_base_context]')
    with patch('negociacion.optimizador.services.build_negotiation_pipeline_config', return_value=_Cfg()), patch(
        'negociacion.optimizador.services.experiments_bridge.resolve_entries', return_value=[]
    ), patch('negociacion.optimizador.services.experiments_bridge.apply_overrides', return_value=(_Cfg(), None)), patch(
        'negociacion.optimizador.services.execute_turn_with_contract',
        return_value=('reply-phase7', state, {'entry_contract': {'entry_surface': 'optimizador'}, 'trace_count': 1}),
    ), patch('negociacion.optimizador.services.experiments_bridge.describe_effective_overrides', return_value={'prompt': {}, 'config': {}, 'contextual': {}}), patch(
        'negociacion.optimizador.services.experiments_bridge.get_state', return_value={'mode': 'mirror', 'workspace_version': 1}
    ), patch('negociacion.optimizador.services.list_turns', return_value=[{'turn_id': 'turn-phase7'}]), patch(
        'negociacion.optimizador.services.derive_turn_title', return_value='Turno 1 · v1'
    ):
        run_payload = optimizer_services.run_sandbox_turn(
            optimizer_session_id='opt-phase7',
            user_id='u_phase7',
            session_id='s_phase7',
            message='hola',
            conversation_id=None,
            scope_turn_id=None,
            repeat_from_turn_id=None,
        )
    print(run_payload)
    print(state.world_state['negotiation_canonical_traces'][-1].get('_optimizador', {}).get('base_context'))

    state_overrides = get_session_state(user_id='u_phase7', session_id='s_phase7')
    state_overrides.world_state['negotiation_canonical_traces'] = [
        {
            'turn_id': 'turn-phase7-overrides',
            'context_meta': {'flow_id': 'negociacion', 'context_id': 'baseline_current', 'context_version': '1.0.0'},
        }
    ]

    print('\n[sandbox_turn_with_overrides_keeps_base_context]')
    with patch('negociacion.optimizador.services.build_negotiation_pipeline_config', return_value=_Cfg()), patch(
        'negociacion.optimizador.services.experiments_bridge.resolve_entries',
        return_value=[{'scope': 'this_optimizer_session', 'category': 'prompt', 'key': 'planner_prompt', 'value': 'override'}],
    ), patch('negociacion.optimizador.services.experiments_bridge.apply_overrides', return_value=(_Cfg(), None)), patch(
        'negociacion.optimizador.services.execute_turn_with_contract',
        return_value=('reply-phase7-override', state_overrides, {'entry_contract': {'entry_surface': 'optimizador'}, 'trace_count': 1}),
    ), patch('negociacion.optimizador.services.experiments_bridge.describe_effective_overrides', return_value={'prompt': {'planner_prompt': 'override'}, 'config': {}, 'contextual': {}}), patch(
        'negociacion.optimizador.services.experiments_bridge.get_state', return_value={'mode': 'sandbox', 'workspace_version': 2}
    ), patch('negociacion.optimizador.services.list_turns', return_value=[{'turn_id': 'turn-phase7-overrides'}]), patch(
        'negociacion.optimizador.services.derive_turn_title', return_value='Turno 2 · v1'
    ):
        run_override_payload = optimizer_services.run_sandbox_turn(
            optimizer_session_id='opt-phase7',
            user_id='u_phase7',
            session_id='s_phase7',
            message='hola otra vez',
            conversation_id='conv-phase7',
            scope_turn_id=None,
            repeat_from_turn_id=None,
        )
    print(run_override_payload)
    print(state_overrides.world_state['negotiation_canonical_traces'][-1].get('_optimizador', {}).get('base_context'))

    print('\nresultado=ok')


if __name__ == '__main__':
    main()
