from __future__ import annotations

from unittest.mock import patch

from interfaz_usuario.services import ensure_session
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from negociacion.optimizador import services as optimizer_services
from sessions.state import SESSIONS, get_session_state


def main() -> None:
    SESSIONS.clear()
    ensure_session(user_id='u_phase5', session_id='s_phase5')
    state = get_session_state(user_id='u_phase5', session_id='s_phase5')
    config = build_negotiation_pipeline_config()

    def fake_turn(current_state, user_message, current_config):
        current_state.world_state[f'{current_config.memory_key}_traces'] = [{'turn_id': 'turn-phase5'}]
        current_state.world_state[current_config.memory_key] = {'openai_thread': {'conversation_id': 'conv-phase5', 'previous_response_id': 'resp-phase5'}}
        return 'reply-phase5', current_state

    with patch('negociacion.orchestration.turn_contract.run_negotiation_cognitive_turn', side_effect=fake_turn):
        _, updated_state, meta = execute_turn_with_contract(
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
    print('[session_context]')
    print(updated_state.world_state['negotiation_context'])
    print('\n[trace_context_meta]')
    print(trace.get('context_meta'))
    print('\n[entry_contract_context_meta]')
    print(meta.get('entry_contract', {}).get('context_meta'))

    state.world_state['optimizador_sandbox_meta'] = {'clone_strategy': 'new_conversation_clean_start'}
    state.world_state['negotiation_canonical_traces'] = [trace]
    cfg = type('Cfg', (), {'memory_key': 'negotiation_canonical'})()
    with patch('negociacion.optimizador.services.build_negotiation_pipeline_config', return_value=cfg), patch(
        'negociacion.optimizador.services.experiments_bridge.resolve_entries', return_value=[{'scope': 'conversation', 'category': 'config', 'key': 'x', 'value': 1}],
    ), patch('negociacion.optimizador.services.experiments_bridge.apply_overrides', return_value=(cfg, None)), patch(
        'negociacion.optimizador.services.execute_turn_with_contract', return_value=('reply', state, {'entry_contract': {'entry_surface': 'optimizador'}, 'trace_count': 1})
    ), patch('negociacion.optimizador.services.experiments_bridge.describe_effective_overrides', return_value={'prompt': {}, 'config': {}, 'contextual': {}}), patch(
        'negociacion.optimizador.services.experiments_bridge.get_state', return_value={'mode': 'mirror', 'workspace_version': 1}
    ), patch('negociacion.optimizador.services.list_turns', return_value=[{'turn_id': 'turn-phase5'}]), patch(
        'negociacion.optimizador.services.derive_turn_title', return_value='Turno 1 · v1'
    ):
        optimizer_services.run_sandbox_turn(
            optimizer_session_id='opt-phase5',
            user_id='u_phase5',
            session_id='s_phase5',
            message='hola',
            conversation_id=None,
            scope_turn_id=None,
            repeat_from_turn_id=None,
        )

    print('\n[optimizer_base_context]')
    print(state.world_state['negotiation_canonical_traces'][-1].get('_optimizador', {}).get('base_context'))
    print('\nresultado=ok')


if __name__ == '__main__':
    main()
