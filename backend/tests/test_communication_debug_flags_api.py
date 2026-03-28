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

    def test_debug_endpoint_exposes_policy_and_runtime_without_secrets(self) -> None:
        with patch.dict(
            os.environ,
            {
                'COMM_DEBUG_FLAGS_ENABLED': 'true',
                'OPENAI_API_KEY': 'sk-test-secret-value',
                'RAILWAY_SERVICE_NAME': 'comm-backend-prod',
                'RAILWAY_ENVIRONMENT_NAME': 'production',
                'GIT_SHA': 'abc123def',
                'COMMUNICATION_FORCE_SAFE_MODE': 'false',
            },
            clear=False,
        ):
            response = self.client.get('/api/comunicacion/debug/llm-flags')

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            set(payload.keys()),
            {'policy_source', 'policy_version', 'effective_policy', 'safety_controls', 'openai', 'runtime_fingerprint'},
        )
        self.assertEqual(payload['policy_source'], 'code')
        self.assertTrue(payload['policy_version'])
        self.assertEqual(payload['effective_policy']['content_mode'], 'llm')
        self.assertEqual(payload['effective_policy']['delivery_mode'], 'llm')
        self.assertEqual(payload['effective_policy']['visual_mode'], 'llm_v1')
        self.assertEqual(payload['effective_policy']['global_synthesis_mode'], 'llm')
        self.assertFalse(payload['safety_controls']['force_safe_mode'])

        self.assertEqual(payload['openai'], {'has_openai_api_key': True})
        self.assertNotIn('OPENAI_API_KEY', str(payload))
        self.assertNotIn('sk-test-secret-value', str(payload))

        self.assertEqual(payload['runtime_fingerprint']['git_sha'], 'abc123def')
        self.assertEqual(payload['runtime_fingerprint']['railway_service_name'], 'comm-backend-prod')
        self.assertEqual(payload['runtime_fingerprint']['railway_environment_name'], 'production')
        self.assertIsInstance(payload['runtime_fingerprint']['pid'], str)


if __name__ == '__main__':
    unittest.main()
