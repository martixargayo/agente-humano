from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.app import app
from comunicacion.storage import REPOSITORY
from sessions.state import SESSIONS


class ComunicacionAttemptApiTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        self.client = TestClient(app, raise_server_exceptions=False)
        boot = self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'iu_api', 'session_id': 'sess_api'})
        self.assertEqual(boot.status_code, 200)

    def test_create_get_and_upload_attempt_flow(self) -> None:
        created = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_api', 'session_id': 'sess_api'})
        self.assertEqual(created.status_code, 200)
        attempt_id = created.json()['attempt_id']
        self.assertEqual(created.json()['status'], 'draft')

        fetched = self.client.get(f'/api/comunicacion/attempts/{attempt_id}', params={'user_id': 'iu_api', 'session_id': 'sess_api'})
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()['attempt_id'], attempt_id)
        self.assertIsNone(fetched.json()['recording_id'])

        uploaded = self.client.post(
            f'/api/comunicacion/attempts/{attempt_id}/upload',
            json={
                'user_id': 'iu_api',
                'session_id': 'sess_api',
                'mime_type': 'video/webm',
                'duration_ms': 92314,
                'video_ref': 'storage://tmp/rec_api/original.webm',
                'poster_frame_ref': 'storage://tmp/rec_api/poster.jpg',
                'capture_meta': {'width': 1280, 'height': 720, 'audio_codec': 'opus'},
            },
        )
        self.assertEqual(uploaded.status_code, 200)
        payload = uploaded.json()
        self.assertEqual(payload['attempt_id'], attempt_id)
        self.assertEqual(payload['status'], 'uploaded')
        self.assertTrue(payload['recording_id'].startswith('rec_'))

    def test_get_attempt_rejects_invalid_ownership(self) -> None:
        created = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_api', 'session_id': 'sess_api'})
        attempt_id = created.json()['attempt_id']
        response = self.client.get(
            f'/api/comunicacion/attempts/{attempt_id}',
            params={'user_id': 'otro_usuario', 'session_id': 'sess_api'},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail']['error'], 'attempt_not_found')

    def test_upload_rejects_invalid_metadata(self) -> None:
        created = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_api', 'session_id': 'sess_api'})
        attempt_id = created.json()['attempt_id']
        response = self.client.post(
            f'/api/comunicacion/attempts/{attempt_id}/upload',
            json={
                'user_id': 'iu_api',
                'session_id': 'sess_api',
                'mime_type': '',
                'duration_ms': 0,
                'video_ref': '',
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail']['error'], 'invalid_recording_metadata')
