from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.app import app
from sessions.state import SESSIONS


class ComunicacionBootstrapApiTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_bootstrap_generates_identity_and_returns_baseline_context(self) -> None:
        response = self.client.post('/api/comunicacion/sessions/bootstrap', json={'public_slug': 'comunicacion'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['user_id'].startswith('iu_'))
        self.assertTrue(payload['session_id'].startswith('sess_'))
        self.assertEqual(payload['session_bootstrap_state'], 'new')
        self.assertFalse(payload['existing_session'])
        self.assertEqual(payload['context_id'], 'baseline_current')
        self.assertEqual(payload['public_slug'], 'comunicacion')
        self.assertEqual(payload['presentation_config']['theme'], 'communication')
        self.assertEqual(payload['activity_brief']['title'], 'Presentación breve grabada')
        self.assertTrue(payload['capture_policy']['allow_rerecord'])

    def test_bootstrap_rehydrates_existing_session(self) -> None:
        first = self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'u1', 'session_id': 's1'})
        second = self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'u1', 'session_id': 's1'})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        payload = second.json()
        self.assertEqual(payload['user_id'], 'u1')
        self.assertEqual(payload['session_id'], 's1')
        self.assertEqual(payload['session_bootstrap_state'], 'rehydrated')
        self.assertTrue(payload['existing_session'])

    def test_unknown_public_slug_returns_404(self) -> None:
        response = self.client.post('/api/comunicacion/sessions/bootstrap', json={'public_slug': 'desconocido'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail']['error'], 'unsupported_public_slug')

    def test_conflicting_surface_returns_409(self) -> None:
        ui_boot = self.client.post('/api/interfaz_usuario/sessions/bootstrap', json={'user_id': 'u_conf', 'session_id': 's_conf'})
        self.assertEqual(ui_boot.status_code, 200)

        response = self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'u_conf', 'session_id': 's_conf'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail']['error'], 'session_surface_conflict')
