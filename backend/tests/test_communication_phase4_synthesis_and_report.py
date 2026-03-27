from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import app
from comunicacion.storage import REPOSITORY
from evaluacion.contracts.communication_models import CommunicationGlobalSynthesisLlmOutputV1
from evaluacion.engine.communication_synthesis import (
    build_global_synthesis_input,
    synthesize_global_communication_feedback,
)
from sessions.state import SESSIONS


class CommunicationPhase4SynthesisAndReportTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        if hasattr(REPOSITORY, '_communication_eval_jobs'):
            REPOSITORY._communication_eval_jobs.clear()
        if hasattr(REPOSITORY, '_communication_eval_reports'):
            REPOSITORY._communication_eval_reports.clear()

    def test_synthesis_weighted_score_and_consistency_penalty(self) -> None:
        content = {'score_0_100': 90, 'status_visual': 'correcto', 'summary': 'Contenido sólido', 'details': [], 'recommendations': ['A']}
        delivery = {'score_0_100': 75, 'status_visual': 'mejorable', 'summary': 'Delivery estable', 'details': [], 'recommendations': ['B']}
        visual = {'score_0_100': 30, 'status_visual': 'mejorable', 'summary': 'Visual débil', 'details': [], 'recommendations': ['C']}
        synthesis_input = build_global_synthesis_input(
            evaluation_id='eval_phase4',
            content_output=content,
            delivery_output=delivery,
            visual_output=visual,
        )
        output, meta = synthesize_global_communication_feedback(synthesis_input=synthesis_input)
        # weighted = 40.5 + 26.25 + 6 = 72.75; spread=60 => penalty 10 => 63
        self.assertEqual(output.score_global_100, 63)
        self.assertEqual(meta.mode, 'fallback')
        self.assertEqual(meta.fallback_reason, 'disabled_flag')
        self.assertNotIn('Fortalezas destacadas', output.summary_short_2_3_lines)
        self.assertNotIn('Prioridades de mejora', output.summary_short_2_3_lines)

    def test_synthesis_llm_output_contract_and_mapping(self) -> None:
        content = {'score_0_100': 84, 'status_visual': 'correcto', 'summary': 'Contenido bien enfocado', 'details': [], 'recommendations': []}
        delivery = {'score_0_100': 80, 'status_visual': 'correcto', 'summary': 'Delivery claro', 'details': [], 'recommendations': []}
        visual = {'score_0_100': 74, 'status_visual': 'mejorable', 'summary': 'Visual correcto con margen', 'details': [], 'recommendations': []}
        synthesis_input = build_global_synthesis_input(
            evaluation_id='eval_phase4_llm',
            content_output=content,
            delivery_output=delivery,
            visual_output=visual,
        )
        llm_output = CommunicationGlobalSynthesisLlmOutputV1(
            score_global_100=84,
            summary_short_2_3_lines='Has construido una comunicación bastante sólida y clara, con varios aciertos visibles, aunque aún puedes afinar el cierre.',
            recommendations=[
                {
                    'title': 'Haz el cierre más intencional',
                    'description': 'Termina con una idea final más clara para reforzar el mensaje principal.',
                }
            ],
        )
        with (
            patch('evaluacion.engine.communication_synthesis._is_global_synthesis_llm_enabled', return_value=True),
            patch('evaluacion.engine.communication_synthesis._run_global_synthesis_llm_openai', return_value=llm_output),
        ):
            output, meta = synthesize_global_communication_feedback(synthesis_input=synthesis_input)

        self.assertEqual(output.score_global_100, 84)
        self.assertEqual(output.summary_short_2_3_lines, llm_output.summary_short_2_3_lines)
        self.assertEqual(meta.mode, 'llm')
        self.assertEqual(meta.fallback_reason, None)
        self.assertEqual(len(output.recommendations), 1)
        self.assertEqual(output.recommendations[0].title, 'Haz el cierre más intencional')

    def test_synthesis_llm_contract_limits_recommendations_to_four(self) -> None:
        with self.assertRaises(ValidationError):
            CommunicationGlobalSynthesisLlmOutputV1(
                score_global_100=70,
                summary_short_2_3_lines='Resumen breve.',
                recommendations=[
                    {'title': 'r1', 'description': 'd1'},
                    {'title': 'r2', 'description': 'd2'},
                    {'title': 'r3', 'description': 'd3'},
                    {'title': 'r4', 'description': 'd4'},
                    {'title': 'r5', 'description': 'd5'},
                ],
            )

    def test_synthesis_llm_allows_zero_recommendations(self) -> None:
        payload = CommunicationGlobalSynthesisLlmOutputV1(
            score_global_100=92,
            summary_short_2_3_lines='Tu comunicación ha sido sólida y consistente, con muy pocos ajustes pendientes.',
            recommendations=[],
        )
        self.assertEqual(payload.recommendations, [])

    def test_synthesis_llm_failure_falls_back_to_rule_based(self) -> None:
        content = {'score_0_100': 90, 'status_visual': 'correcto', 'summary': 'Contenido sólido', 'details': [], 'recommendations': ['A']}
        delivery = {'score_0_100': 75, 'status_visual': 'mejorable', 'summary': 'Delivery estable', 'details': [], 'recommendations': ['B']}
        visual = {'score_0_100': 30, 'status_visual': 'mejorable', 'summary': 'Visual débil', 'details': [], 'recommendations': ['C']}
        synthesis_input = build_global_synthesis_input(
            evaluation_id='eval_phase4_llm_fallback',
            content_output=content,
            delivery_output=delivery,
            visual_output=visual,
        )
        with (
            patch('evaluacion.engine.communication_synthesis._is_global_synthesis_llm_enabled', return_value=True),
            patch('evaluacion.engine.communication_synthesis._run_global_synthesis_llm_openai', side_effect=RuntimeError('forced_failure')),
        ):
            output, meta = synthesize_global_communication_feedback(synthesis_input=synthesis_input)
        self.assertEqual(output.score_global_100, 63)
        self.assertEqual(meta.mode, 'fallback')
        self.assertEqual(meta.fallback_reason, 'unexpected_error')
        self.assertLessEqual(len(output.recommendations), 4)

    def test_report_includes_global_synthesis_and_uses_its_score(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'iu_phase4', 'session_id': 'sess_phase4'})
        attempt = client.post('/api/comunicacion/attempts', json={'user_id': 'iu_phase4', 'session_id': 'sess_phase4'}).json()
        client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/upload",
            json={
                'user_id': 'iu_phase4',
                'session_id': 'sess_phase4',
                'mime_type': 'video/webm',
                'duration_ms': 11000,
                'video_ref': 'client-temp://sess_phase4/att/report.webm',
                'capture_meta': {'provisional_client_ref': True},
            },
        )
        submit = client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/submit",
            json={'user_id': 'iu_phase4', 'session_id': 'sess_phase4'},
        ).json()

        evaluation_id = submit['evaluation_id']
        for _ in range(40):
            status = client.get(f'/api/comunicacion/evaluations/{evaluation_id}').json()
            if status['status'] == 'completed':
                break
            time.sleep(0.05)

        report = client.get(f'/api/comunicacion/evaluations/{evaluation_id}/report').json()
        self.assertIn('global_synthesis', report)
        self.assertIsInstance(report['global_synthesis']['score_global_100'], int)
        self.assertEqual(report['header']['score_global_100'], report['global_synthesis']['score_global_100'])
        self.assertNotIn('Fortalezas destacadas', report['header']['summary_2_3_lines'])
        self.assertNotIn('Prioridades de mejora', report['header']['summary_2_3_lines'])


if __name__ == '__main__':
    unittest.main()
