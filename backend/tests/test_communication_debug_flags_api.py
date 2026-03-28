from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app


class CommunicationDebugFlagsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_debug_endpoint_returns_404_when_flag_is_off(self) -> None:
        with patch.dict(os.environ, {'COMM_DEBUG_FLAGS_ENABLED': 'false'}, clear=False):
            response = self.client.get('/api/comunicacion/debug/llm-flags')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail']['error'], 'debug_endpoint_not_enabled')

    def test_debug_endpoint_exposes_raw_and_parsed_without_secrets(self) -> None:
        with patch.dict(
            os.environ,
            {
                'COMM_DEBUG_FLAGS_ENABLED': 'true',
                'COMM_CONTENT_OPENAI_ENABLED': ' true ',
                'COMM_AUDIO_OPENAI_ENABLED': 'off',
                'COMM_SYNTHESIS_OPENAI_ENABLED': 'enabled',
                'COMM_VISUAL_MODE': 'llm_v1',
                'COMM_VISUAL_OPENAI_ENABLED': '1',
                'OPENAI_API_KEY': 'sk-test-secret-value',
                'RAILWAY_SERVICE_NAME': 'comm-backend-prod',
                'RAILWAY_ENVIRONMENT_NAME': 'production',
                'GIT_SHA': 'abc123def',
            },
            clear=False,
        ):
            response = self.client.get('/api/comunicacion/debug/llm-flags')

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            set(payload.keys()),
            {'raw_env', 'parsed_env', 'openai', 'runtime_fingerprint'},
        )

        self.assertEqual(payload['raw_env']['COMM_CONTENT_OPENAI_ENABLED'], 'true')
        self.assertEqual(payload['raw_env']['COMM_AUDIO_OPENAI_ENABLED'], 'off')
        self.assertEqual(payload['raw_env']['COMM_SYNTHESIS_OPENAI_ENABLED'], 'enabled')
        self.assertEqual(payload['raw_env']['COMM_VISUAL_MODE'], 'llm_v1')
        self.assertEqual(payload['raw_env']['COMM_VISUAL_OPENAI_ENABLED'], '1')

        self.assertTrue(payload['parsed_env']['content_llm_enabled'])
        self.assertFalse(payload['parsed_env']['audio_llm_enabled'])
        self.assertFalse(payload['parsed_env']['global_synthesis_llm_enabled'])
        self.assertEqual(payload['parsed_env']['visual_mode'], 'llm_v1')
        self.assertTrue(payload['parsed_env']['visual_llm_enabled'])

        self.assertEqual(payload['openai'], {'has_openai_api_key': True})
        self.assertNotIn('OPENAI_API_KEY', payload['raw_env'])
        self.assertNotIn("'openai_api_key':", str(payload).lower())
        self.assertNotIn('sk-test-secret-value', str(payload))

        self.assertEqual(payload['runtime_fingerprint']['git_sha'], 'abc123def')
        self.assertEqual(payload['runtime_fingerprint']['railway_service_name'], 'comm-backend-prod')
        self.assertEqual(payload['runtime_fingerprint']['railway_environment_name'], 'production')
        self.assertIsInstance(payload['runtime_fingerprint']['pid'], str)


if __name__ == '__main__':
    unittest.main()
