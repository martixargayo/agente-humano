from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluacion.contracts.models import FeedbackReportCoreV1, TrajectoryTurn, TurnTrajectoryV1
from evaluacion.domains.negotiation.assets_loader import resolve_negotiation_evaluation_assets
from evaluacion.domains.negotiation.context_resolver import resolve_evaluation_context_from_session
from evaluacion.domains.negotiation.extractor import build_feedback_input_bundle_v1
from evaluacion.domains.negotiation.rubric_loader import load_negotiation_rubric_v1
from evaluacion.engine.input_shaping import shape_core_input, shape_trajectory_input
from evaluacion.engine.service import _run_pipeline_from_bundle
from evaluacion.storage import REPOSITORY
from negociacion.contexts import resolve_default_negotiation_context
from sessions.state import SESSIONS, SessionState, get_session_state

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_CORE_PROMPT = REPO_ROOT / 'backend' / 'evaluacion' / 'prompts' / 'core_evaluator_prompt.txt'
LEGACY_TRAJECTORY_PROMPT = REPO_ROOT / 'backend' / 'evaluacion' / 'prompts' / 'trajectory_evaluator_prompt.txt'
LEGACY_RUBRIC = REPO_ROOT / 'backend' / 'evaluacion' / 'domains' / 'negotiation' / 'rubrics' / 'negotiation_rubric_v1.json'


class Phase6EvaluationContextAwareTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        REPOSITORY._jobs.clear()
        REPOSITORY._reports.clear()

    def _seed_history(self, state: SessionState) -> None:
        state.history = [
            {'role': 'user', 'content': 'hola'},
            {'role': 'assistant', 'content': 'buenas, dime'},
            {'role': 'user', 'content': 'te ofrezco 7000 euros'},
            {'role': 'assistant', 'content': 'necesito algo más de margen'},
        ]

    def test_bundle_baseline_contains_context_identity(self) -> None:
        from interfaz_usuario.services import ensure_session

        ensure_session(user_id='u_eval', session_id='s_eval')
        state = get_session_state(user_id='u_eval', session_id='s_eval')
        self._seed_history(state)

        bundle = build_feedback_input_bundle_v1(state=state, evaluation_id='eval-1')

        self.assertEqual(bundle.domain_context.flow_id, 'negociacion')
        self.assertEqual(bundle.domain_context.context_id, 'baseline_current')
        self.assertEqual(bundle.domain_context.context_version, '1.0.0')

    def test_baseline_prompts_resolve_equivalent_to_legacy(self) -> None:
        default_context = resolve_default_negotiation_context()
        assets = resolve_negotiation_evaluation_assets(
            type('DomainContextStub', (), {'context_id': default_context.context_id, 'flow_id': default_context.flow_id, 'context_version': default_context.context_version})()
        )

        self.assertEqual(assets.core_prompt_path.read_text(encoding='utf-8'), LEGACY_CORE_PROMPT.read_text(encoding='utf-8'))
        self.assertEqual(assets.trajectory_prompt_path.read_text(encoding='utf-8'), LEGACY_TRAJECTORY_PROMPT.read_text(encoding='utf-8'))

    def test_baseline_rubric_resolves_equivalent_to_legacy(self) -> None:
        rubric = load_negotiation_rubric_v1()
        legacy_payload = json.loads(LEGACY_RUBRIC.read_text(encoding='utf-8'))
        self.assertEqual(rubric.model_dump(mode='json'), legacy_payload)

    def test_legacy_session_without_binding_falls_back_to_baseline(self) -> None:
        legacy_state = SessionState(user_id='u_legacy_eval', session_id='s_legacy_eval')
        self._seed_history(legacy_state)
        SESSIONS[('u_legacy_eval', 's_legacy_eval')] = legacy_state

        context = resolve_evaluation_context_from_session(legacy_state)
        bundle = build_feedback_input_bundle_v1(state=legacy_state, evaluation_id='eval-legacy')

        self.assertEqual(context.context_id, 'baseline_current')
        self.assertEqual(bundle.domain_context.context_id, 'baseline_current')

    def test_pipeline_report_shape_remains_compatible_and_provenance_carries_context(self) -> None:
        from interfaz_usuario.services import ensure_session

        ensure_session(user_id='u_report', session_id='s_report')
        state = get_session_state(user_id='u_report', session_id='s_report')
        self._seed_history(state)
        bundle = build_feedback_input_bundle_v1(state=state, evaluation_id='eval-report')

        core_output = FeedbackReportCoreV1.model_validate({
            'schema_version': 'feedback_report_core.v1',
            'score_global_100': 66,
            'interaction_outcome': 'partial_progress',
            'summary_2_3_lines': 'Resumen estable baseline.',
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

        REPOSITORY.create_job(evaluation_id='eval-report', user_id='u_report', session_id='s_report', created_at='2026-03-19T00:00:00+00:00')
        with patch('evaluacion.engine.service.run_core_evaluator', return_value=(core_output, 'model')), patch(
            'evaluacion.engine.service.run_trajectory_evaluator', return_value=(trajectory_output, 'model')
        ):
            _run_pipeline_from_bundle(evaluation_id='eval-report', bundle=bundle)

        report = REPOSITORY.get_report(evaluation_id='eval-report')
        self.assertIsNotNone(report)
        self.assertEqual(report.schema_version, 'ui_feedback_report.v1')
        self.assertEqual(report.provenance.context_id, 'baseline_current')
        self.assertEqual(report.header.summary_2_3_lines, 'Resumen estable baseline.')

    def test_shape_inputs_keep_context_aware_resolution_without_visible_baseline_change(self) -> None:
        from interfaz_usuario.services import ensure_session

        ensure_session(user_id='u_shape', session_id='s_shape')
        state = get_session_state(user_id='u_shape', session_id='s_shape')
        self._seed_history(state)
        bundle = build_feedback_input_bundle_v1(state=state, evaluation_id='eval-shape')

        core_input = shape_core_input(bundle)
        trajectory_input = shape_trajectory_input(bundle)

        self.assertEqual(core_input.domain_context.context_id, 'baseline_current')
        self.assertEqual(trajectory_input.domain_context.context_id, 'baseline_current')
        self.assertEqual(core_input.domain_rubric.metadata.rubric_version, '1.0.0')
