from __future__ import annotations

import json
from pathlib import Path

from evaluacion.contracts.models import FeedbackReportCoreV1, Provenance, TrajectoryTurn, TurnTrajectoryV1
from evaluacion.engine.assembler import assemble_ui_report
from evaluacion.engine.reconciliation import reconcile_outputs

REPO_ROOT = Path(__file__).resolve().parents[2]
CTX_DIR = REPO_ROOT / 'backend' / 'conversacion_simple' / 'contexts' / 'conversacion-dificil-periodista' / 'evaluation'
RUBRIC_PATH = CTX_DIR / 'rubric.json'
CORE_PROMPT_PATH = CTX_DIR / 'core_evaluator_prompt.txt'
TRAJ_PROMPT_PATH = CTX_DIR / 'trajectory_evaluator_prompt.txt'
FEEDBACK_VIEW_JS = REPO_ROOT / 'backend' / 'interfaz_usuario_app' / 'feedback_report_view.js'


def _core_output(outcome: str = 'partial_progress') -> FeedbackReportCoreV1:
    return FeedbackReportCoreV1.model_validate({
        'schema_version': 'feedback_report_core.v1',
        'score_global_100': 70,
        'interaction_outcome': outcome,
        'summary_2_3_lines': 'Resumen de prueba.',
        'evaluation_blocks': [
            {'block_id': 'valores', 'title': 'A', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
            {'block_id': 'vision', 'title': 'B', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
            {'block_id': 'relacion', 'title': 'C', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
            {'block_id': 'proceso', 'title': 'D', 'status_visual': 'correcto', 'score_0_100': 70, 'checks': [{'polarity': 'check', 'micro_explanation': 'ok', 'evidence_turn_indexes': [1]}], 'block_verdict': 'ok'},
        ],
        'best_moment': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
        'most_delicate_moment': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
        'turning_point': {'turn_index': 1, 'why': 'ok', 'impact': 'ok'},
        'recommendations': [{'title': 't', 'description': 'd', 'example': None}],
    })


def test_difficult_context_assets_include_new_titles_and_conviction_contract() -> None:
    rubric = json.loads(RUBRIC_PATH.read_text(encoding='utf-8'))
    blocks = {row['block_id']: row['title'] for row in rubric['blocks']}

    assert blocks['valores'] == 'Entrar sin juzgar ni confrontar'
    assert blocks['vision'] == 'Preguntar para descubrir'
    assert blocks['relacion'] == 'Reformular ideas'
    assert blocks['proceso'] == 'Llegar a un acuerdo conjunto'

    core_prompt = CORE_PROMPT_PATH.read_text(encoding='utf-8')
    assert 'cambio de pensamiento y conducta' in core_prompt
    assert '1) valores (Entrar sin juzgar ni confrontar)' in core_prompt

    trajectory_prompt = TRAJ_PROMPT_PATH.read_text(encoding='utf-8')
    assert 'conviction_level_0_100' in trajectory_prompt
    assert 'debe ser >= 75' in trajectory_prompt
    assert 'debe ser claramente menor de 75' in trajectory_prompt
    assert 'debe coincidir exactamente' in trajectory_prompt


def test_reconciliation_enforces_conviction_thresholds_and_last_point_in_difficult_context() -> None:
    trajectory = TurnTrajectoryV1(
        schema_version='turn_trajectory.v1',
        conviction_level_0_100=62,
        trajectory=[
            TrajectoryTurn(turn_index=1, agreement_closeness_score_0_100=40, user_excerpt='u1', counterpart_excerpt='a1', impact_reason='i1', counterpart_thought_effect='c1', better_rephrase=None),
            TrajectoryTurn(turn_index=2, agreement_closeness_score_0_100=62, user_excerpt='u2', counterpart_excerpt='a2', impact_reason='i2', counterpart_thought_effect='c2', better_rephrase=None),
        ],
    )

    out_agreement = reconcile_outputs(
        core=_core_output(outcome='agreement_reached'),
        trajectory=trajectory,
        turn_count=2,
        context_id='conversacion-dificil-periodista',
    )
    assert out_agreement.conviction_level_0_100 >= 75
    assert out_agreement.trajectory[-1].agreement_closeness_score_0_100 == out_agreement.conviction_level_0_100

    out_no_agreement = reconcile_outputs(
        core=_core_output(outcome='no_agreement'),
        trajectory=trajectory,
        turn_count=2,
        context_id='conversacion-dificil-periodista',
    )
    assert out_no_agreement.conviction_level_0_100 < 75
    assert out_no_agreement.trajectory[-1].agreement_closeness_score_0_100 == out_no_agreement.conviction_level_0_100


def test_assembler_and_frontend_contract_expose_conviction_metric() -> None:
    trajectory = TurnTrajectoryV1(
        schema_version='turn_trajectory.v1',
        conviction_level_0_100=82,
        trajectory=[
            TrajectoryTurn(turn_index=1, agreement_closeness_score_0_100=55, user_excerpt='u1', counterpart_excerpt='a1', impact_reason='i1', counterpart_thought_effect='c1', better_rephrase=None),
            TrajectoryTurn(turn_index=2, agreement_closeness_score_0_100=82, user_excerpt='u2', counterpart_excerpt='a2', impact_reason='i2', counterpart_thought_effect='c2', better_rephrase=None),
        ],
    )

    report = assemble_ui_report(
        core=_core_output(),
        trajectory=trajectory,
        provenance=Provenance.model_validate({
            'evaluation_id': 'eval-x',
            'bundle_hash': 'b',
            'core_input_hash': 'ci',
            'trajectory_input_hash': 'ti',
            'core_output_hash': 'co',
            'trajectory_output_hash': 'to',
            'core_model': 'm1',
            'trajectory_model': 'm2',
            'core_prompt_version': 'v1',
            'trajectory_prompt_version': 'v1',
            'flow_id': 'conversacion_simple',
            'context_id': 'conversacion-dificil-periodista',
            'context_version': '1.0.0',
            'resolution_source': 'session_binding',
            'fallback_used': False,
        }),
    )

    assert report.header.conviction_level_0_100 == 82

    feedback_js = FEEDBACK_VIEW_JS.read_text(encoding='utf-8')
    assert 'DIFFICULT_CONTEXT_ID' in feedback_js
    assert 'Nivel de convencimiento' in feedback_js
    assert 'Evolución del convencimiento al cambio' in feedback_js
