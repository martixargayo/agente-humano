from __future__ import annotations

import time
import unittest

from fastapi.testclient import TestClient

from api.app import app
from comunicacion.storage import REPOSITORY
from sessions.state import SESSIONS


class CommunicationStatusApiTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        if hasattr(REPOSITORY, '_communication_eval_jobs'):
            REPOSITORY._communication_eval_jobs.clear()
        if hasattr(REPOSITORY, '_communication_eval_reports'):
            REPOSITORY._communication_eval_reports.clear()
        self.client = TestClient(app, raise_server_exceptions=False)
        self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'iu_status', 'session_id': 'sess_status'})

    def _create_completed_evaluation(self) -> str:
        attempt = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_status', 'session_id': 'sess_status'}).json()
        self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/upload",
            json={
                'user_id': 'iu_status',
                'session_id': 'sess_status',
                'mime_type': 'video/webm',
                'duration_ms': 9000,
                'video_ref': 'client-temp://sess_status/att/report.webm',
                'capture_meta': {'provisional_client_ref': True},
            },
        )
        submit = self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/submit",
            json={'user_id': 'iu_status', 'session_id': 'sess_status'},
        ).json()
        evaluation_id = submit['evaluation_id']
        for _ in range(40):
            status = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}').json()
            if status['status'] == 'completed':
                return evaluation_id
            time.sleep(0.05)
        self.fail('evaluation did not complete in time')

    def test_status_endpoint_returns_expected_shape(self) -> None:
        evaluation_id = self._create_completed_evaluation()
        response = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['evaluation_id'], evaluation_id)
        self.assertIn(payload['status'], ['running', 'completed'])
        self.assertIn(
            payload['stage'],
            [
                'queued',
                'extracting',
                'extracting_media',
                'transcription_started',
                'transcript_ready',
                'content_analysis_ready',
                'audio_metrics_started',
                'audio_features_ready',
                'delivery_analysis_ready',
                'visual_placeholder_ready',
                'assembling_report',
                'completed',
            ],
        )
        self.assertTrue(payload['report_available'])
        self.assertIsNone(payload['error'])

    def test_report_endpoint_returns_basic_stable_json(self) -> None:
        evaluation_id = self._create_completed_evaluation()
        response = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}/report')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['schema_version'], 'ui_communication_report.v1')
        self.assertEqual(payload['evaluation_id'], evaluation_id)
        self.assertIn('header', payload)
        self.assertIn('media', payload)
        self.assertIn('video_panel', payload)
        self.assertIn('block_cards', payload)
        self.assertIn('exports', payload)
