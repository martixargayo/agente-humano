from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.app import app
from comunicacion.services.session_service import COMMUNICATION_RUNTIME_WORLD_STATE_KEY
from comunicacion.storage import REPOSITORY
from sessions.state import SESSIONS, get_session_state


class ComunicacionSessionRefsTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        self.client = TestClient(app, raise_server_exceptions=False)
        response = self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'iu_refs', 'session_id': 'sess_refs'})
        self.assertEqual(response.status_code, 200)

    def test_session_only_keeps_lightweight_runtime_refs(self) -> None:
        created = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_refs', 'session_id': 'sess_refs'})
        attempt_id = created.json()['attempt_id']
        uploaded = self.client.post(
            f'/api/comunicacion/attempts/{attempt_id}/upload',
            json={
                'user_id': 'iu_refs',
                'session_id': 'sess_refs',
                'mime_type': 'video/webm',
                'duration_ms': 92314,
                'video_ref': 'storage://tmp/rec_refs/original.webm',
                'poster_frame_ref': 'storage://tmp/rec_refs/poster.jpg',
                'capture_meta': {'width': 1280, 'height': 720, 'audio_codec': 'opus'},
            },
        )
        self.assertEqual(uploaded.status_code, 200)
        recording_id = uploaded.json()['recording_id']

        state = get_session_state(user_id='iu_refs', session_id='sess_refs')
        runtime = state.world_state[COMMUNICATION_RUNTIME_WORLD_STATE_KEY]

        self.assertEqual(runtime['active_attempt_id'], attempt_id)
        self.assertEqual(runtime['last_recording_id'], recording_id)
        self.assertEqual(runtime['capture_status'], 'uploaded')
        self.assertNotIn('blob', runtime)
        self.assertNotIn('transcript', runtime)
        self.assertNotIn('video_base64', runtime)
        self.assertNotIn('frames', runtime)
