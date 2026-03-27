from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.app import app
from comunicacion.storage import REPOSITORY
from comunicacion.storage.models import RecordingRecord
from evaluacion.engine.communication_media_processing import resolve_recording_media_source
from sessions.state import SESSIONS


class CommunicationRailwayDirectPlaceholderDiagnosisTests(unittest.TestCase):
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
        self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'iu_diag', 'session_id': 'sess_diag'})

    def test_client_temp_video_ref_is_not_resolvable_by_backend_media_source(self) -> None:
        recording = RecordingRecord(
            recording_id='rec_diag_scheme',
            attempt_id='att_diag_scheme',
            user_id='iu_diag',
            session_id='sess_diag',
            mime_type='video/webm',
            duration_ms=8000,
            video_ref='client-temp://sess_diag/att_diag/1710000000000.webm',
            capture_meta={'provisional_client_ref': True},
            created_at=datetime.now(timezone.utc),
        )

        with self.assertRaises(HTTPException) as raised:
            resolve_recording_media_source(recording=recording)

        detail = raised.exception.detail
        self.assertEqual(detail['error'], 'recording_media_scheme_not_supported')
        self.assertEqual(detail['scheme'], 'client-temp')

    def test_public_direct_capture_flow_completes_with_placeholder_blocks_when_video_ref_is_client_temp(self) -> None:
        attempt = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_diag', 'session_id': 'sess_diag'}).json()
        self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/upload",
            json={
                'user_id': 'iu_diag',
                'session_id': 'sess_diag',
                'mime_type': 'video/webm',
                'duration_ms': 12000,
                'video_ref': 'client-temp://sess_diag/att_diag/1710000000000.webm',
                'capture_meta': {'provisional_client_ref': True},
            },
        )

        submit = self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/submit",
            json={'user_id': 'iu_diag', 'session_id': 'sess_diag'},
        ).json()
        evaluation_id = submit['evaluation_id']

        for _ in range(40):
            status = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}').json()
            if status['status'] == 'completed':
                break
            time.sleep(0.05)

        report = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}/report').json()
        self.assertEqual(report['media']['video_ref'], 'client-temp://sess_diag/att_diag/1710000000000.webm')

        content = next(block for block in report['block_cards'] if block['block_id'] == 'contenido')
        delivery = next(block for block in report['block_cards'] if block['block_id'] == 'delivery')
        visual = next(block for block in report['block_cards'] if block['block_id'] == 'visual')

        self.assertEqual(content['score_0_100'], 55)
        self.assertIn('degradada por ausencia de transcripción real', content['summary'])
        self.assertIn('Transcripción no disponible en modo real; se usó señal placeholder para contenido.', content['details'])

        self.assertEqual(delivery['score_0_100'], 40)
        self.assertIn('degradada', delivery['summary'].lower())
        self.assertIn('No hay extracción acústica real todavía; las métricas son placeholders sintéticos para estabilizar contratos y stages.', delivery['details'])

        self.assertEqual(visual['score_0_100'], 50)
        self.assertIn('degradada', visual['summary'].lower())
        self.assertIn('No hay frame manifest real disponible; evaluación visual degradada a modo placeholder.', visual['details'])
        self.assertIn('branch_runtime_meta', report)
        self.assertEqual(report['branch_runtime_meta']['global_synthesis']['mode'], 'fallback')


if __name__ == '__main__':
    unittest.main()
