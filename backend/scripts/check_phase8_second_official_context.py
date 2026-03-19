from __future__ import annotations

from unittest.mock import patch

from evaluacion.contracts.models import FeedbackReportCoreV1, TrajectoryTurn, TurnTrajectoryV1
from evaluacion.domains.negotiation.assets_loader import resolve_negotiation_evaluation_assets
from evaluacion.domains.negotiation.extractor import build_feedback_input_bundle_v1
from evaluacion.engine.service import _run_pipeline_from_bundle
from evaluacion.storage import REPOSITORY
from interfaz_usuario import services as ui_services
from negociacion.contexts import resolve_default_negotiation_context, resolve_negotiation_context, resolve_public_context_selection
from negociacion.optimizador import services as optimizer_services
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from sessions.state import SESSIONS, get_session_state

NEW_CONTEXT_ID = 'validacion_multicontexto'
NEW_PUBLIC_SLUG = 'negociacion-validacion'


def _seed_history(state) -> None:
    state.history = [
        {'role': 'user', 'content': 'hola'},
        {'role': 'assistant', 'content': 'buenas, dime'},
        {'role': 'user', 'content': 'te ofrezco 7000 euros'},
        {'role': 'assistant', 'content': 'necesito algo más de margen'},
    ]


def main() -> None:
    SESSIONS.clear()
    REPOSITORY._jobs.clear()
    REPOSITORY._reports.clear()

    print('[baseline_context_resolved]')
    print(resolve_default_negotiation_context().model_dump(mode='json'))

    print('\n[new_context_resolved]')
    print(resolve_negotiation_context(NEW_CONTEXT_ID).model_dump(mode='json'))

    print('\n[bootstrap_by_context_id_new]')
    payload_context = ui_services.ensure_session(user_id='u_p8_ctx', session_id='s_p8_ctx', context_id=NEW_CONTEXT_ID)
    print(payload_context)

    print('\n[bootstrap_by_public_slug_new]')
    payload_slug = ui_services.ensure_session(user_id='u_p8_slug', session_id='s_p8_slug', public_slug=NEW_PUBLIC_SLUG)
    print(payload_slug)
    print(resolve_public_context_selection(public_slug=NEW_PUBLIC_SLUG).model_dump(mode='json'))

    print('\n[session_binding_new_context]')
    print(get_session_state(user_id='u_p8_ctx', session_id='s_p8_ctx').world_state['negotiation_context'])

    print('\n[explicit_conflict_baseline_vs_new]')
    ui_services.ensure_session(user_id='u_p8_conflict', session_id='s_p8_conflict', context_id='baseline_current')
    try:
        ui_services.ensure_session(user_id='u_p8_conflict', session_id='s_p8_conflict', context_id=NEW_CONTEXT_ID)
    except Exception as exc:
        print(getattr(exc, 'detail', str(exc)))

    print('\n[runtime_trace_new_context]')
    ui_services.ensure_session(user_id='u_p8_runtime', session_id='s_p8_runtime', context_id=NEW_CONTEXT_ID)
    state_runtime = get_session_state(user_id='u_p8_runtime', session_id='s_p8_runtime')
    config = build_negotiation_pipeline_config(context_id=NEW_CONTEXT_ID)

    def fake_turn(current_state, user_message, current_config):
        current_state.world_state[f'{current_config.memory_key}_traces'] = [{'turn_id': 'turn-p8-runtime'}]
        current_state.world_state[current_config.memory_key] = {'openai_thread': {}}
        return 'reply-runtime', current_state

    with patch('negociacion.orchestration.turn_contract.run_negotiation_cognitive_turn', side_effect=fake_turn):
        _, updated_state, _ = execute_turn_with_contract(
            state=state_runtime,
            user_message='hola',
            config=config,
            contract=TurnEntryContract(
                entry_surface='interfaz_usuario',
                entrypoint='/api/interfaz_usuario/negociacion/turn',
                overrides_applied=False,
                optimizer_wrapper_used=False,
            ),
        )
    print(updated_state.world_state['negotiation_canonical_traces'][-1].get('context_meta'))

    print('\n[evaluation_new_context]')
    _seed_history(state_runtime)
    bundle = build_feedback_input_bundle_v1(state=state_runtime, evaluation_id='eval-p8')
    assets = resolve_negotiation_evaluation_assets(bundle.domain_context)
    print(bundle.domain_context.model_dump(mode='json'))
    print({'core_prompt_path': str(assets.core_prompt_path), 'trajectory_prompt_path': str(assets.trajectory_prompt_path), 'rubric_path': str(assets.rubric_path)})

    core_output = FeedbackReportCoreV1.model_validate({
        'schema_version': 'feedback_report_core.v1',
        'score_global_100': 70,
        'interaction_outcome': 'partial_progress',
        'summary_2_3_lines': 'Resumen contexto alternativo.',
        'evaluation_blocks': [
            {'block_id': 'valores', 'title': 'Valores', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
            {'block_id': 'vision', 'title': 'Visión', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
            {'block_id': 'relacion', 'title': 'Relación', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
            {'block_id': 'proceso', 'title': 'Proceso', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
        ],
        'best_moment': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
        'most_delicate_moment': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
        'turning_point': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
        'recommendations': [{'title': 't', 'description': 'd', 'example': {'original_excerpt': 'x', 'better_rephrase': 'y'}}],
    })
    trajectory_output = TurnTrajectoryV1(schema_version='turn_trajectory.v1', trajectory=[
        TrajectoryTurn(turn_index=1, agreement_closeness_score_0_100=60, user_excerpt='u', counterpart_excerpt='a', impact_reason='i', counterpart_thought_effect='c', better_rephrase='b')
    ])
    REPOSITORY.create_job(evaluation_id='eval-p8', user_id='u_p8_runtime', session_id='s_p8_runtime', created_at='2026-03-19T00:00:00+00:00')
    with patch('evaluacion.engine.service.run_core_evaluator', return_value=(core_output, 'model')), patch(
        'evaluacion.engine.service.run_trajectory_evaluator', return_value=(trajectory_output, 'model')
    ):
        _run_pipeline_from_bundle(evaluation_id='eval-p8', bundle=bundle)
    print(REPOSITORY.get_report(evaluation_id='eval-p8').provenance.model_dump(mode='json'))

    print('\n[optimizer_new_context]')
    optimizer_boot = optimizer_services.ensure_session(user_id='u_p8_opt', session_id='s_p8_opt', context_id=NEW_CONTEXT_ID)
    optimizer_clone = optimizer_services.duplicate_sandbox_session(
        optimizer_session_id='opt-p8',
        source_user_id='u_p8_opt',
        source_session_id='s_p8_opt',
        source_conversation_id='conv-p8',
    )
    optimizer_new = optimizer_services.new_conversation_session(
        optimizer_session_id='opt-p8',
        user_id='u_p8_opt',
        session_id='s_p8_opt',
    )
    print(optimizer_boot)
    print(optimizer_clone)
    print(optimizer_new)

    state_opt = get_session_state(user_id='u_p8_opt', session_id='s_p8_opt')
    state_opt.world_state['optimizador_sandbox_meta'] = {'clone_strategy': 'full_session_with_preferred_conversation'}
    state_opt.world_state['negotiation_canonical_traces'] = [
        {'turn_id': 'turn-p8-opt', 'context_meta': {'flow_id': 'negociacion', 'context_id': NEW_CONTEXT_ID, 'context_version': '1.0.0'}}
    ]

    with patch('negociacion.optimizador.services.build_negotiation_pipeline_config', return_value=build_negotiation_pipeline_config(context_id=NEW_CONTEXT_ID)), patch(
        'negociacion.optimizador.services.experiments_bridge.resolve_entries', return_value=[]
    ), patch('negociacion.optimizador.services.experiments_bridge.apply_overrides', return_value=(build_negotiation_pipeline_config(context_id=NEW_CONTEXT_ID), None)), patch(
        'negociacion.optimizador.services.execute_turn_with_contract',
        return_value=('reply-opt-p8', state_opt, {'entry_contract': {'entry_surface': 'optimizador'}, 'trace_count': 1}),
    ), patch('negociacion.optimizador.services.experiments_bridge.describe_effective_overrides', return_value={'prompt': {}, 'config': {}, 'contextual': {}}), patch(
        'negociacion.optimizador.services.experiments_bridge.get_state', return_value={'mode': 'mirror', 'workspace_version': 1}
    ), patch('negociacion.optimizador.services.list_turns', return_value=[{'turn_id': 'turn-p8-opt'}]), patch(
        'negociacion.optimizador.services.derive_turn_title', return_value='Turno 1 · v1'
    ):
        optimizer_turn = optimizer_services.run_sandbox_turn(
            optimizer_session_id='opt-p8',
            user_id='u_p8_opt',
            session_id='s_p8_opt',
            message='hola',
            conversation_id=None,
            scope_turn_id=None,
            repeat_from_turn_id=None,
        )
    print(optimizer_turn)
    print(state_opt.world_state['negotiation_canonical_traces'][-1].get('_optimizador', {}).get('base_context'))

    print('\nresultado=ok')


if __name__ == '__main__':
    main()
