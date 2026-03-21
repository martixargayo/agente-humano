from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / 'backend' / 'scripts' / 'validate_snapshot_pipeline.js'


class SnapshotPipelineValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            ['node', str(SCRIPT)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.results = json.loads(completed.stdout)

    def test_feedback_pipeline_resolution_and_fallbacks(self) -> None:
        feedback = self.results['feedback']

        self.assertEqual(feedback['resolveCaptureRoot']['liveSource'], 'live-root')
        self.assertTrue(feedback['resolveCaptureRoot']['liveIsRoot'])
        self.assertEqual(feedback['resolveCaptureRoot']['detachedSource'], 'sandbox-root')
        self.assertTrue(feedback['resolveCaptureRoot']['detachedUsesSandbox'])
        self.assertEqual(feedback['resolveCaptureRoot']['bodyAppendCount'], 1)

        self.assertEqual(feedback['waitForReportImages']['total'], 3)
        self.assertEqual(feedback['waitForReportImages']['decoded'], 3)
        self.assertEqual(feedback['waitForReportImages']['pending'], 0)

        self.assertTrue(feedback['primarySuccess']['ok'])
        self.assertEqual(feedback['primarySuccess']['result']['strategy'], 'dom-data-url')
        self.assertEqual(feedback['primarySuccess']['result']['source'], 'live-root')
        self.assertIsNone(feedback['primarySuccess']['result']['recoveredFrom'])

        self.assertTrue(feedback['longPrimarySuccess']['ok'])
        self.assertEqual(feedback['longPrimarySuccess']['result']['height'], 1420)

        self.assertTrue(feedback['sandboxFallback']['ok'])
        self.assertEqual(feedback['sandboxFallback']['result']['strategy'], 'svg-data-fallback')
        self.assertEqual(feedback['sandboxFallback']['result']['source'], 'sandbox-root')
        self.assertEqual(feedback['sandboxFallback']['result']['recoveredFrom'][0]['engine'], 'dom-data-url')

        self.assertFalse(feedback['allFail']['ok'])
        self.assertIn('dom-data-url', feedback['allFail']['error'])
        self.assertIn('svg-data-fallback', feedback['allFail']['error'])

    def test_app_payload_and_embed_flow(self) -> None:
        app = self.results['app']

        self.assertTrue(app['captureSuccess']['payloadHasPng'])
        self.assertEqual(app['captureSuccess']['snapshotPrefix'], 'data:image/png;base64,')
        self.assertIn('<html><body><h1>', app['captureSuccess']['reportHtml'])
        self.assertGreater(app['captureSuccess']['stats']['nonWhitePixels'], 100)

        self.assertTrue(app['captureFailure']['payloadHasPng'])
        self.assertTrue(app['captureFailure']['usesPlaceholder'])
        self.assertGreater(app['captureFailure']['stats']['nonWhitePixels'], 100)
        self.assertGreater(app['captureFailure']['stats']['opaquePixels'], 100)

        self.assertTrue(app['missingApi']['payloadHasPng'])
        self.assertGreater(app['missingApi']['stats']['nonWhitePixels'], 100)
        self.assertGreater(app['missingApi']['stats']['opaquePixels'], 100)

        self.assertEqual(app['emitLifecycle']['envelopeTypes'], ['final_result_available', 'final_result'])
        self.assertTrue(app['emitLifecycle']['finalPayloadHasPng'])

    def test_artifacts_exist(self) -> None:
        app = self.results['app']
        for key in ('captureSuccess', 'captureFailure', 'missingApi'):
            artifact = Path(app[key]['artifact'])
            self.assertTrue(artifact.exists(), f'No existe artefacto {artifact}')
            self.assertGreater(artifact.stat().st_size, 200, f'Artefacto demasiado pequeño: {artifact}')


if __name__ == '__main__':
    unittest.main()
