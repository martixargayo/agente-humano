from __future__ import annotations

import unittest


class CommunicationReportRendererSourceTests(unittest.TestCase):
    def test_report_view_exposes_final_renderer_video_panel_and_export_helpers(self) -> None:
        source = open('backend/comunicacion_app/report_view.js', 'r', encoding='utf-8').read()
        for marker in [
            'function renderCommunicationReport(root, report, options = {})',
            'function renderCommunicationVideoPanel(media, options = {})',
            'function resolveCommunicationVideoSrc(media)',
            'function serializeCommunicationReportToHtml(report)',
            'async function captureCommunicationReportPngDataUrl(report, options = {})',
            'async function captureCommunicationReportPngDataUrlFromDom(report, options = {})',
            'function buildCommunicationReportSyntheticFallbackPngDataUrl(report, options = {})',
            'class="comm-report__video-meta"',
            '<video class="comm-report__video" controls',
            "if (fallback.startsWith('file://')) return '';",
        ]:
            self.assertIn(marker, source)
