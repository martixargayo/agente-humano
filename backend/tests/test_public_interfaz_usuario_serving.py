from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.app import app


class PublicInterfazUsuarioServingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_public_pages_and_assets_work_for_baseline_and_slugged_entries(self) -> None:
        expected_scripts = [
            '/interfaz_usuario/feedback_report_view.js',
            '/interfaz_usuario/avatar_runtime/bootstrap.js',
            '/interfaz_usuario/app.js',
        ]

        for path in [
            '/interfaz_usuario',
            '/interfaz_usuario/',
            '/interfaz_usuario/negociacion',
            '/interfaz_usuario/negociacion/',
            '/interfaz_usuario/negociacion-validacion',
            '/interfaz_usuario/negociacion-validacion/',
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            body = response.text
            for script_path in expected_scripts:
                self.assertIn(script_path, body, path)

        app_js = self.client.get('/interfaz_usuario/app.js')
        feedback_js = self.client.get('/interfaz_usuario/feedback_report_view.js')
        avatar_bootstrap_js = self.client.get('/interfaz_usuario/avatar_runtime/bootstrap.js')

        self.assertEqual(app_js.status_code, 200)
        self.assertIn('function readPublicSlugFromUrl()', app_js.text)
        self.assertIn('function bootstrapPayload()', app_js.text)

        self.assertEqual(feedback_js.status_code, 200)
        self.assertIn('global.FeedbackReportView = {', feedback_js.text)
        self.assertIn('renderReport,', feedback_js.text)
        self.assertIn('serializeReportToHtml', feedback_js.text)
        self.assertIn('downloadReportPng', feedback_js.text)
        self.assertIn('captureReportAsPng', feedback_js.text)

        self.assertEqual(avatar_bootstrap_js.status_code, 200)
        self.assertIn('createAvatarRuntime', avatar_bootstrap_js.text)

    def test_slugged_asset_paths_no_longer_require_nested_files(self) -> None:
        response = self.client.get('/interfaz_usuario/negociacion-validacion/')
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertNotIn('./app.js', body)
        self.assertNotIn('./feedback_report_view.js', body)
        self.assertNotIn('./avatar_runtime/bootstrap.js', body)
        self.assertIn('/interfaz_usuario/app.js', body)
        self.assertIn('/interfaz_usuario/feedback_report_view.js', body)
        self.assertIn('/interfaz_usuario/avatar_runtime/bootstrap.js', body)

    def test_report_screen_hides_export_actions_and_keeps_embed_final_result_messages(self) -> None:
        page = self.client.get('/interfaz_usuario/')
        self.assertEqual(page.status_code, 200)
        body = page.text
        self.assertNotIn('id="feedbackDownloadHtmlBtn"', body)
        self.assertNotIn('id="feedbackDownloadJsonBtn"', body)
        self.assertNotIn('id="feedbackDownloadPngBtn"', body)
        self.assertNotIn('id="feedbackBackBtn"', body)

        app_js = self.client.get('/interfaz_usuario/app.js')
        self.assertEqual(app_js.status_code, 200)
        self.assertIn("emitEmbedMessage('final_result_available'", app_js.text)
        self.assertIn("emitEmbedMessage('final_result', payload)", app_js.text)
        self.assertIn('function downloadCurrentReport(format)', app_js.text)
        self.assertIn('summary_html: serializedHtml', app_js.text)
        self.assertIn('payloadjson: report', app_js.text)
