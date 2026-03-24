from __future__ import annotations

import time
import unittest

from fastapi.testclient import TestClient

from api.app import app
from comunicacion.storage import REPOSITORY
from evaluacion.engine.communication_service import list_communication_job_stages
from sessions.state import SESSIONS


class CommunicationEvaluationJobTests(unittest.TestCase):
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
        boot = self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'iu_job', 'session_id': 'sess_job'})
        self.assertEqual(boot.status_code, 200)

    def test_submit_creates_evaluation_and_eventually_persists_report(self) -> None:
        attempt = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_job', 'session_id': 'sess_job'}).json()
        upload = self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/upload",
            json={
                'user_id': 'iu_job',
                'session_id': 'sess_job',
                'mime_type': 'video/webm',
                'duration_ms': 13000,
                'video_ref': 'client-temp://sess_job/att/one.webm',
                'capture_meta': {'provisional_client_ref': True},
            },
        )
        self.assertEqual(upload.status_code, 200)

        submit = self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/submit",
            json={'user_id': 'iu_job', 'session_id': 'sess_job'},
        )
        self.assertEqual(submit.status_code, 200)
        submit_payload = submit.json()
        self.assertTrue(submit_payload['evaluation_id'].startswith('eval_'))
        self.assertIn(submit_payload['status'], ['queued', 'running', 'completed'])

        seen_stages = set()
        final_status = None
        for _ in range(40):
            status = self.client.get(f"/api/comunicacion/evaluations/{submit_payload['evaluation_id']}")
            self.assertEqual(status.status_code, 200)
            payload = status.json()
            seen_stages.add(payload['stage'])
            final_status = payload
            if payload['status'] == 'completed':
                break
            time.sleep(0.05)

        self.assertIsNotNone(final_status)
        self.assertEqual(final_status['status'], 'completed')
        self.assertTrue(final_status['report_available'])
        self.assertTrue(seen_stages.issubset(set(list_communication_job_stages()) | {'failed'}))
        self.assertTrue({'queued', 'extracting', 'completed'}.intersection(seen_stages))

        report = self.client.get(f"/api/comunicacion/evaluations/{submit_payload['evaluation_id']}/report")
        self.assertEqual(report.status_code, 200)
        report_payload = report.json()
        self.assertEqual(report_payload['evaluation_id'], submit_payload['evaluation_id'])
        self.assertEqual(report_payload['schema_version'], 'ui_communication_report.v1')
        self.assertIn('header', report_payload)
        self.assertIn('video_panel', report_payload)
