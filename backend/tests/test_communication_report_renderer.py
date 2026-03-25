from __future__ import annotations

import unittest


class CommunicationReportRendererSourceTests(unittest.TestCase):
    def test_report_view_exposes_final_renderer_video_panel_and_export_helpers(self) -> None:
        source = open('backend/comunicacion_app/report_view.js', 'r', encoding='utf-8').read()
        for marker in [
            'function renderCommunicationReport(root, report, options = {})',
            'function renderCommunicationVideoPanel(media, panel, options = {})',
            'function serializeCommunicationReportToHtml(report)',
            'async function captureCommunicationReportPngDataUrl(report, options = {})',
            'class="comm-report__video-panel"',
            '<video class="comm-report__video" controls',
        ]:
            self.assertIn(marker, source)
