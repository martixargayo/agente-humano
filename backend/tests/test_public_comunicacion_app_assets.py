from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.app import app


class PublicComunicacionAppAssetsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_index_contains_main_capture_containers(self) -> None:
        response = self.client.get('/comunicacion')
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('id="screenIntro"', body)
        self.assertIn('id="screenPermissions"', body)
        self.assertIn('id="screenPreview"', body)
        self.assertIn('id="screenRecording"', body)
        self.assertIn('id="screenReview"', body)
        self.assertIn('id="screenUploading"', body)
        self.assertIn('id="screenProcessing"', body)
        self.assertIn('id="reportPlaceholderRoot"', body)
        self.assertIn('id="previewVideo"', body)
        self.assertIn('id="reviewVideo"', body)

    def test_app_js_exposes_state_markers_and_frontend_entrypoints(self) -> None:
        response = self.client.get('/comunicacion/app.js')
        self.assertEqual(response.status_code, 200)
        source = response.text
        for marker in [
            "SCREEN_INTRO = 'intro'",
            "SCREEN_PERMISSIONS = 'permissions'",
            "SCREEN_PREVIEW = 'preview'",
            "SCREEN_RECORDING = 'recording'",
            "SCREEN_REVIEW = 'review'",
            'async function bootstrapCommunicationSession()',
            'async function requestCapturePermissions()',
            'async function openPreviewStream(',
            'async function createAttempt()',
            'async function startRecording()',
            'async function stopRecording()',
            'async function registerRecordingMetadata()',
            'function transitionTo(screen)',
            'function renderApp()',
            'client-temp://',
        ]:
            self.assertIn(marker, source)

    def test_report_view_and_styles_cover_final_report_layout(self) -> None:
        report_js = self.client.get('/comunicacion/report_view.js')
        styles_css = self.client.get('/comunicacion/styles.css')
        self.assertEqual(report_js.status_code, 200)
        self.assertEqual(styles_css.status_code, 200)
        self.assertIn('renderCommunicationReportPlaceholder', report_js.text)
        self.assertIn('renderCommunicationReport(root, report, options = {})', report_js.text)
        self.assertIn('captureCommunicationReportPngDataUrl', report_js.text)
        self.assertIn('.video-shell', styles_css.text)
        self.assertIn('.comm-report__video-panel', styles_css.text)
        self.assertIn('.recording-indicator', styles_css.text)
        self.assertIn('.communication-banner--error', styles_css.text)
