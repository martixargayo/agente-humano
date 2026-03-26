from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.app import app


class PublicComunicacionServingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_public_pages_and_assets_work_for_root_and_slugged_entries(self) -> None:
        for path in ['/comunicacion', '/comunicacion/', '/comunicacion/comunicacion', '/comunicacion/comunicacion/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            body = response.text
            self.assertIn('/comunicacion/app.js', body)
            self.assertIn('/comunicacion/report_view.js', body)
            self.assertIn('/comunicacion/styles.css', body)
            self.assertIn('id="screenSetup"', body)
            self.assertIn('id="communicationLoadingScreen"', body)
            self.assertIn('id="communicationReportScreen"', body)
            self.assertNotIn('id="screenProcessing"', body)

        app_js = self.client.get('/comunicacion/app.js')
        report_js = self.client.get('/comunicacion/report_view.js')
        styles_css = self.client.get('/comunicacion/styles.css')

        self.assertEqual(app_js.status_code, 200)
        self.assertIn('CommunicationApp', app_js.text)
        self.assertIn('bootstrapCommunicationSession', app_js.text)
        self.assertIn("SCREEN_REVIEW = 'review'", app_js.text)
        self.assertIn("SCREEN_SETUP = 'setup'", app_js.text)
        self.assertIn("buildCommunicationEmbedEnvelope('final_result_available'", app_js.text)
        self.assertIn("buildCommunicationFinalAvailabilityPayload", app_js.text)
        self.assertIn("showCommunicationView(mode)", app_js.text)

        self.assertEqual(report_js.status_code, 200)
        self.assertIn('CommunicationReportView', report_js.text)
        self.assertIn('renderCommunicationReportPlaceholder', report_js.text)
        self.assertIn('renderCommunicationReport(root, report, options = {})', report_js.text)

        self.assertEqual(styles_css.status_code, 200)
        self.assertIn('.communication-shell', styles_css.text)
        self.assertIn('.communication-card', styles_css.text)
        self.assertIn('.comm-report__video-panel', styles_css.text)
        self.assertIn('.feedback-screen', styles_css.text)
