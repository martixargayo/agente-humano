from __future__ import annotations

import unittest


class CommunicationReportExportContractSourceTests(unittest.TestCase):
    def test_frontend_app_exposes_export_actions_for_json_html_and_png(self) -> None:
        source = open('backend/comunicacion_app/app.js', 'r', encoding='utf-8').read()
        for marker in [
            'async function exportReportJson()',
            'async function exportReportHtml()',
            'async function exportReportPng()',
            'serializeCommunicationReportToHtml(state.report.payload)',
            'captureCommunicationReportPngDataUrl(state.report.payload)',
            "exportReportJsonBtn",
            "exportReportHtmlBtn",
            "exportReportPngBtn",
        ]:
            self.assertIn(marker, source)
