from __future__ import annotations

import time
import unittest

from fastapi.testclient import TestClient

from api.app import app
from comunicacion.storage import REPOSITORY
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
        output = synthesize_global_communication_feedback(synthesis_input=synthesis_input)
        # weighted = 40.5 + 26.25 + 6 = 72.75; spread=60 => penalty 10 => 63
        self.assertEqual(output.global_score_0_100, 63)
        self.assertTrue(output.top_strengths)
        self.assertTrue(output.priority_improvements)
        self.assertTrue(output.action_plan)
        self.assertIn('dispersión', ' '.join(output.consistency_notes))

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
        self.assertIsInstance(report['global_synthesis']['global_score_0_100'], int)
        self.assertEqual(report['header']['score_global_100'], report['global_synthesis']['global_score_0_100'])


if __name__ == '__main__':
    unittest.main()
