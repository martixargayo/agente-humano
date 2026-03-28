from __future__ import annotations

import time
import unittest

from fastapi.testclient import TestClient

from api.app import app
from comunicacion.storage import REPOSITORY
from sessions.state import SESSIONS


class CommunicationReportContractTests(unittest.TestCase):
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
        self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'iu_report', 'session_id': 'sess_report'})

    def _completed_report(self) -> dict:
        attempt = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_report', 'session_id': 'sess_report'}).json()
        self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/upload",
            json={
                'user_id': 'iu_report',
                'session_id': 'sess_report',
                'mime_type': 'video/webm',
                'duration_ms': 14000,
                'video_ref': 'client-temp://sess_report/att/report.webm',
                'capture_meta': {'provisional_client_ref': True},
            },
        )
        submit = self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/submit",
            json={'user_id': 'iu_report', 'session_id': 'sess_report'},
        ).json()
        evaluation_id = submit['evaluation_id']
        for _ in range(40):
            status = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}').json()
            if status['status'] == 'completed':
                break
            time.sleep(0.05)
        response = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}/report')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_report_contract_includes_media_video_panel_timeline_and_exports(self) -> None:
        payload = self._completed_report()
        self.assertEqual(payload['schema_version'], 'ui_communication_report.v1')
        self.assertIn('header', payload)
        self.assertIn('media', payload)
        self.assertEqual(payload['media']['player_hint']['placement'], 'top_right')
        self.assertEqual(payload['media']['playback_url'], f"/api/comunicacion/recordings/{payload['recording_id']}/video")
        self.assertIn('video_panel', payload)
        self.assertEqual(payload['video_panel']['default_mode'], 'embedded_small_player')
        self.assertIn('block_cards', payload)
        self.assertIn('timeline', payload)
        self.assertIn('recommendations', payload)
        self.assertIn('global_synthesis', payload)
        self.assertIn('score_global_100', payload['global_synthesis'])
        self.assertIn('summary_short_2_3_lines', payload['global_synthesis'])
        self.assertIn('recommendations', payload['global_synthesis'])
        self.assertIn('content_aida_feedback', payload)
        self.assertIsInstance(payload['content_aida_feedback'], dict)
        for key in ('attention', 'interest', 'development', 'action'):
            self.assertIn(key, payload['content_aida_feedback'])
            self.assertIn('score_1_3', payload['content_aida_feedback'][key])
            self.assertIn('label', payload['content_aida_feedback'][key])
            self.assertIn('reason_short', payload['content_aida_feedback'][key])
        self.assertIn('audio_specialized_feedback', payload)
        if payload['audio_specialized_feedback'] is not None:
            self.assertIsInstance(payload['audio_specialized_feedback'], dict)
            self.assertIn('score_1_5', payload['audio_specialized_feedback'])
            self.assertIn('label', payload['audio_specialized_feedback'])
            self.assertIn('reason_short', payload['audio_specialized_feedback'])
        self.assertIn('visual_specialized_feedback', payload)
        if payload['visual_specialized_feedback'] is not None:
            self.assertIsInstance(payload['visual_specialized_feedback'], dict)
            self.assertIn('score_1_5', payload['visual_specialized_feedback'])
            self.assertIn('label', payload['visual_specialized_feedback'])
            self.assertIn('reason_short', payload['visual_specialized_feedback'])
        self.assertIn('branch_runtime_meta', payload)
        self.assertIn('contenido', payload['branch_runtime_meta'])
        self.assertIn('delivery', payload['branch_runtime_meta'])
        self.assertIn('visual', payload['branch_runtime_meta'])
        self.assertIn('global_synthesis', payload['branch_runtime_meta'])
        self.assertIn('provenance', payload)
        self.assertIn('exports', payload)
        self.assertTrue(payload['exports']['summary_html'].startswith('<!doctype html>'))
        self.assertTrue(payload['exports']['report_snapshot_png_data_url'].startswith('data:image/png;base64,'))
