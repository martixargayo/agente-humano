from __future__ import annotations

import time
import unittest

from fastapi.testclient import TestClient

from api.app import app
from comunicacion.storage import REPOSITORY
from sessions.state import SESSIONS


class CommunicationReportApiTests(unittest.TestCase):
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
        self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'iu_api', 'session_id': 'sess_api'})

    def test_report_api_returns_final_phase5_shape(self) -> None:
        attempt = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_api', 'session_id': 'sess_api'}).json()
        self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/upload",
            json={
                'user_id': 'iu_api',
                'session_id': 'sess_api',
                'mime_type': 'video/webm',
                'duration_ms': 11000,
                'video_ref': 'client-temp://sess_api/att/final.webm',
                'capture_meta': {'provisional_client_ref': True},
            },
        )
        submit = self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/submit",
            json={'user_id': 'iu_api', 'session_id': 'sess_api'},
        ).json()
        evaluation_id = submit['evaluation_id']
        for _ in range(40):
            status = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}').json()
            if status['status'] == 'completed':
                break
            time.sleep(0.05)
        response = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}/report')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['evaluation_id'], evaluation_id)
        self.assertEqual(payload['media']['recording_id'], payload['recording_id'])
        self.assertEqual(payload['media']['playback_url'], f"/api/comunicacion/recordings/{payload['recording_id']}/video")
        self.assertGreaterEqual(payload['header']['score_global_100'], 0)
        self.assertTrue(len(payload['block_cards']) >= 3)
        self.assertTrue(len(payload['timeline']['segments']) >= 1)
        self.assertTrue(len(payload['recommendations']['items']) >= 1)
