from __future__ import annotations

import unittest


class CommunicationReportRendererSourceTests(unittest.TestCase):
    def test_report_view_exposes_final_renderer_video_panel_and_export_helpers(self) -> None:
        source = open('backend/comunicacion_app/report_view.js', 'r', encoding='utf-8').read()
        for marker in [
            'function renderCommunicationReport(root, report, options = {})',
            'function renderCommunicationVideoPanel(media, options = {})',
            'function resolveAidaCards(contentAidaFeedback)',
            'function resolveSpecializedFeedback(raw, options)',
            'function resolveCommunicationVideoSrc(media)',
            'function serializeCommunicationReportToHtml(report)',
            'async function captureCommunicationReportPngDataUrl(report, options = {})',
            'async function captureCommunicationReportPngDataUrlFromDom(report, options = {})',
            'function buildCommunicationReportSyntheticFallbackPngDataUrl(report, options = {})',
            'payload.content_aida_feedback',
            'payload.audio_specialized_feedback',
            'payload.visual_specialized_feedback',
            '<video class="comm-report__video" controls',
            "if (fallback.startsWith('file://')) return '';",
        ]:
            self.assertIn(marker, source)
        self.assertNotIn('resolveAidaCards(blockCards)', source)
        self.assertNotIn('function findByKeyword(items, keywords)', source)
        self.assertNotIn('Por qué esta nota:', source)
        self.assertNotIn('Lo más fuerte:', source)
        self.assertNotIn('Prioridad de mejora:', source)
        self.assertNotIn('Sección preparada; pendiente de mayor granularidad en el contrato actual.', source)
        self.assertNotIn('<dt>recording_id</dt>', source)
        self.assertNotIn('<dt>video_ref</dt>', source)
        self.assertIn('block_cards remains in `/report` for compatibility', source)
