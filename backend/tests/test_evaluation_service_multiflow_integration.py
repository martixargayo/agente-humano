from __future__ import annotations

from unittest.mock import patch

from evaluacion.contracts.models import FeedbackReportCoreV1, TrajectoryTurn, TurnTrajectoryV1
from evaluacion.engine.service import _run_pipeline
from evaluacion.storage import REPOSITORY
from sessions.state import SESSIONS, SessionState


def _seed_history(state: SessionState) -> None:
    state.history = [
        {'role': 'user', 'content': 'hola'},
        {'role': 'assistant', 'content': 'buenas'},
        {'role': 'user', 'content': 'necesito coordinar la sala'},
        {'role': 'assistant', 'content': 'vamos a ordenarlo'},
    ]


def _core_output() -> FeedbackReportCoreV1:
    return FeedbackReportCoreV1.model_validate(
        {
            'schema_version': 'feedback_report_core.v1',
            'score_global_100': 71,
            'interaction_outcome': 'partial_progress',
            'summary_2_3_lines': 'ok',
            'evaluation_blocks': [
                {'block_id': 'valores', 'title': 'Valores', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
                {'block_id': 'vision', 'title': 'Visión', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
                {'block_id': 'relacion', 'title': 'Relación', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
                {'block_id': 'proceso', 'title': 'Proceso', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
            ],
            'best_moment': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
            'most_delicate_moment': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
            'turning_point': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
            'recommendations': [],
        }
    )


def _trajectory_output() -> TurnTrajectoryV1:
    return TurnTrajectoryV1(
        schema_version='turn_trajectory.v1',
        trajectory=[
            TrajectoryTurn(
                turn_index=1,
                agreement_closeness_score_0_100=60,
                user_excerpt='u',
                counterpart_excerpt='a',
                impact_reason='ok',
                counterpart_thought_effect='ok',
                better_rephrase='ok',
            )
        ],
    )


def test_service_pipeline_end_to_end_uses_conversacion_simple_router_and_provenance() -> None:
    SESSIONS.clear()
    REPOSITORY._jobs.clear()
    REPOSITORY._reports.clear()

    state = SessionState(user_id='u_cs_int', session_id='s_cs_int')
    state.world_state['conversacion_simple_context'] = {'flow_id': 'conversacion_simple', 'context_id': 'negociacion_sala_reuniones', 'context_version': '1.0.0'}
    _seed_history(state)
    SESSIONS[(state.user_id, state.session_id)] = state

    REPOSITORY.create_job(evaluation_id='eval-cs-int', user_id=state.user_id, session_id=state.session_id, created_at='2026-04-09T00:00:00+00:00')

    with patch('evaluacion.engine.service.run_core_evaluator', return_value=(_core_output(), 'model')), patch(
        'evaluacion.engine.service.run_trajectory_evaluator', return_value=(_trajectory_output(), 'model')
    ):
        _run_pipeline(evaluation_id='eval-cs-int', user_id=state.user_id, session_id=state.session_id)

    job = REPOSITORY.get_job(evaluation_id='eval-cs-int')
    report = REPOSITORY.get_report(evaluation_id='eval-cs-int')

    assert job is not None
    assert report is not None
    assert report.provenance.flow_id == 'conversacion_simple'
    assert report.provenance.context_id == 'negociacion_sala_reuniones'
    assert report.provenance.resolution_source
    assert 'flow_id' in job.artifacts
    assert job.artifacts['flow_id'] == 'conversacion_simple'


def test_service_pipeline_fails_explicitly_without_binding_or_legacy_signal() -> None:
    SESSIONS.clear()
    REPOSITORY._jobs.clear()
    REPOSITORY._reports.clear()

    state = SessionState(user_id='u_none', session_id='s_none')
    _seed_history(state)
    SESSIONS[(state.user_id, state.session_id)] = state

    REPOSITORY.create_job(evaluation_id='eval-none', user_id=state.user_id, session_id=state.session_id, created_at='2026-04-09T00:00:00+00:00')

    import pytest
    with pytest.raises(RuntimeError, match='evaluation_flow_resolution_error'):
        _run_pipeline(evaluation_id='eval-none', user_id=state.user_id, session_id=state.session_id)
