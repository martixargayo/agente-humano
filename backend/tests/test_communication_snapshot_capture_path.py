from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_VIEW_JS = REPO_ROOT / 'backend' / 'comunicacion_app' / 'report_view.js'


class CommunicationSnapshotCapturePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = REPORT_VIEW_JS.read_text(encoding='utf-8')

    def _extract_function_source(self, name: str) -> str:
        source = self.source
        marker = f'async function {name}' if f'async function {name}' in source else f'function {name}'
        start = source.find(marker)
        self.assertNotEqual(start, -1, f'No se encontró {name}')
        params_end = source.find(')', start)
        brace_start = source.find('{', params_end)

        depth = 0
        in_single = False
        in_double = False
        in_template = False
        escaped = False
        idx = brace_start
        while idx < len(source):
            ch = source[idx]
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif in_single:
                if ch == "'":
                    in_single = False
            elif in_double:
                if ch == '"':
                    in_double = False
            elif in_template:
                if ch == '`':
                    in_template = False
            else:
                if ch == "'":
                    in_single = True
                elif ch == '"':
                    in_double = True
                elif ch == '`':
                    in_template = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return source[start:idx + 1]
            idx += 1
        self.fail(f'No se pudo extraer {name}')

    def _run_harness(self, from_dom_mode: str) -> dict:
        capture_fn = self._extract_function_source('captureCommunicationReportPngDataUrl')
        script = textwrap.dedent(
            f"""
            const calls = [];
            const console = {{ warn: (...args) => calls.push(['warn', ...args]) }};
            async function captureCommunicationReportPngDataUrlFromDom() {{
              calls.push(['fromDom']);
              if ({json.dumps(from_dom_mode)} === 'throw') throw new Error('dom-failed');
              return 'data:image/png;base64,RE9NX1NOT1Q=';
            }}
            function buildCommunicationReportSyntheticFallbackPngDataUrl() {{
              calls.push(['fallback']);
              return 'data:image/png;base64,RkFMTEJBQ0s=';
            }}
            {capture_fn}
            (async () => {{
              const value = await captureCommunicationReportPngDataUrl({{}}, {{}});
              process.stdout.write(JSON.stringify({{ value, calls }}));
            }})();
            """
        )
        completed = subprocess.run(
            ['node', '-e', script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def _run_sanitization_harness(self) -> dict:
        sanitize_fn = self._extract_function_source('sanitizeCaptureCloneForRasterization')
        script = textwrap.dedent(
            f"""
            class FakeNode {{
              constructor(kind) {{
                this.kind = kind;
                this.removed = false;
              }}
              remove() {{
                this.removed = true;
              }}
            }}
            class FakeSection extends FakeNode {{
              constructor(hasMedia) {{
                super('section');
                this.hasMedia = hasMedia;
              }}
              querySelector(selector) {{
                if (!this.hasMedia) return null;
                if (selector.includes('video') || selector.includes('.comm-report__video-meta')) return new FakeNode('media-inside');
                return null;
              }}
            }}
            class FakeRoot {{
              constructor() {{
                this.sections = [new FakeSection(true), new FakeSection(false)];
                this.mediaNodes = [new FakeNode('video'), new FakeNode('meta')];
              }}
              querySelectorAll(selector) {{
                if (selector === '.fb-card.fb-section') return this.sections;
                if (selector.includes('video') || selector.includes('.comm-report__video-meta')) return this.mediaNodes;
                return [];
              }}
            }}
            {sanitize_fn}
            const root = new FakeRoot();
            const summary = sanitizeCaptureCloneForRasterization(root);
            process.stdout.write(JSON.stringify({{
              summary,
              sectionRemovedFlags: root.sections.map((s) => s.removed),
              mediaRemovedFlags: root.mediaNodes.map((n) => n.removed),
            }}));
            """
        )
        completed = subprocess.run(
            ['node', '-e', script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def _run_style_collection_harness(self) -> dict:
        collect_fn = self._extract_function_source('collectCaptureStyles')
        script = textwrap.dedent(
            f"""
            const global = {{
              document: {{
                styleSheets: [
                  {{
                    cssRules: [
                      {{ type: 1, selectorText: 'body', cssText: 'body {{ font-family: Inter, system-ui, sans-serif; }}' }},
                      {{ type: 1, selectorText: '.feedback-dashboard', cssText: '.feedback-dashboard {{ display: grid; gap: 18px; }}' }},
                      {{ type: 1, selectorText: '.fb-card', cssText: '.fb-card {{ border: 1px solid #e4e7ec; }}' }},
                      {{ type: 1, selectorText: '.fb-grid-cards', cssText: '.fb-grid-cards {{ display: grid; }}' }},
                      {{ type: 1, selectorText: '.unrelated-widget', cssText: '.unrelated-widget {{ color: red; }}' }}
                    ]
                  }}
                ]
              }}
            }};
            {collect_fn}
            const matchedSelectors = new Set([
              '.comm-feedback-root',
              '.feedback-dashboard',
              '.fb-card',
              '.fb-grid-cards'
            ]);
            const captureRoot = {{
              matches(selector) {{
                return matchedSelectors.has(String(selector || '').trim());
              }},
              querySelector(selector) {{
                return matchedSelectors.has(String(selector || '').trim()) ? {{}} : null;
              }}
            }};
            const css = collectCaptureStyles(captureRoot);
            process.stdout.write(JSON.stringify({{
              css,
              hasBodyFontFamily: css.includes('font-family: Inter'),
              hasFeedbackDashboardLayout: css.includes('.feedback-dashboard') && css.includes('display: grid'),
              hasFbCardRules: css.includes('.fb-card {{ border'),
              hasFbGridCardsRules: css.includes('.fb-grid-cards {{ display: grid; }}'),
              includesUnrelatedSelector: css.includes('.unrelated-widget')
            }}));
            """
        )
        completed = subprocess.run(
            ['node', '-e', script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def _run_svg_font_family_harness(self) -> dict:
        build_svg_fn = self._extract_function_source('buildCaptureSvgMarkup')
        script = textwrap.dedent(
            f"""
            function collectCaptureStyles() {{
              return '.feedback-dashboard {{ display:grid; }}';
            }}
            {build_svg_fn}
            const clonedRoot = {{
              style: {{}},
              outerHTML: '<section class="comm-feedback-root" data-report-root="true"><div class="feedback-dashboard">ok</div></section>'
            }};
            const svg = buildCaptureSvgMarkup(clonedRoot, 1180, 720);
            process.stdout.write(JSON.stringify({{
              svgHasFontFamilyRule: svg.includes('font-family: Inter, system-ui'),
              svgHasCaptureFrameRule: svg.includes('.comm-report-capture-frame'),
              svgKeepsCollectedStyles: svg.includes('.feedback-dashboard {{ display:grid; }}'),
              clonedRootFontFamily: clonedRoot.style.fontFamily || null
            }}));
            """
        )
        completed = subprocess.run(
            ['node', '-e', script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def test_happy_path_uses_dom_capture_as_primary_strategy(self) -> None:
        output = self._run_harness(from_dom_mode='ok')
        self.assertEqual(output['value'], 'data:image/png;base64,RE9NX1NOT1Q=')
        self.assertEqual(output['calls'], [['fromDom']])

    def test_fallback_is_used_when_dom_capture_fails(self) -> None:
        output = self._run_harness(from_dom_mode='throw')
        self.assertEqual(output['value'], 'data:image/png;base64,RkFMTEJBQ0s=')
        self.assertEqual(output['calls'][0], ['fromDom'])
        self.assertIn(['fallback'], output['calls'])

    def test_dom_capture_sanitizes_video_related_nodes_before_rasterization(self) -> None:
        self.assertIn('const sanitization = sanitizeCaptureCloneForRasterization(clonedRoot);', self.source)
        self.assertIn("section.querySelector('video, audio, iframe, object, embed, .comm-report__video-meta')", self.source)
        self.assertIn("clonedRoot.querySelectorAll('video, audio, iframe, object, embed, .comm-report__video-meta')", self.source)
        output = self._run_sanitization_harness()
        self.assertEqual(output['summary'], {'removed_sections': 1, 'removed_nodes': 2})
        self.assertEqual(output['sectionRemovedFlags'], [True, False])
        self.assertEqual(output['mediaRemovedFlags'], [True, True])

    def test_style_collection_embeds_feedback_layout_and_typography_rules(self) -> None:
        self.assertIn('const captureStyles = collectCaptureStyles(clonedRoot);', self.source)
        output = self._run_style_collection_harness()
        self.assertTrue(output['hasBodyFontFamily'])
        self.assertTrue(output['hasFeedbackDashboardLayout'])
        self.assertTrue(output['hasFbCardRules'])
        self.assertTrue(output['hasFbGridCardsRules'])
        self.assertFalse(output['includesUnrelatedSelector'])

    def test_svg_markup_forces_font_family_on_capture_subtree(self) -> None:
        output = self._run_svg_font_family_harness()
        self.assertTrue(output['svgHasFontFamilyRule'])
        self.assertTrue(output['svgHasCaptureFrameRule'])
        self.assertTrue(output['svgKeepsCollectedStyles'])
        self.assertIn('Inter, system-ui', output['clonedRootFontFamily'])


if __name__ == '__main__':
    unittest.main()
