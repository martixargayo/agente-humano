from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_JS = REPO_ROOT / 'backend' / 'comunicacion_app' / 'app.js'


class CommunicationReportExportsIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = APP_JS.read_text(encoding='utf-8')

    def _extract_function_source(self, name: str) -> str:
        source = self.source
        async_marker = f'async function {name}'
        marker = async_marker if async_marker in source else f'function {name}'
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

    def _run_exports_harness(self) -> dict:
        functions = [
            'stableStringifyForHash',
            'simpleHashString',
            'deriveCommunicationFinalPayloadHash',
            'buildCommunicationFinalResultPayload',
        ]
        extracted = '\n\n'.join(self._extract_function_source(name) for name in functions)
        script = textwrap.dedent(
            f"""
            const state = {{
              session: {{ session_id: 'sess-200', context_id: 'ctx-200', public_slug: 'comunicacion', user_id: 'user-200' }},
              attempt: {{ attempt_id: 'attempt-200' }},
              evaluation: {{ evaluation_id: 'eval-200' }},
            }};
            const exportedHtml = '<html><body><h1>Informe</h1><p>Resumen HTML</p></body></html>';
            const exportedJson = {{ format: 'json', sections: 4, recommendations: ['respirar', 'mirar cámara'] }};
            const exportedSnapshot = 'data:image/png;base64,ZXhwb3J0LXBuZw==';
            const window = {{
              CommunicationReportView: {{
                serializeCommunicationReportToHtml() {{
                  return exportedHtml;
                }},
                async captureCommunicationReportPngDataUrl() {{
                  return exportedSnapshot;
                }},
              }},
            }};
            globalThis.window = window;
            globalThis.global = window;
            {extracted}
            const report = {{
              attempt_id: 'attempt-200',
              recording_id: 'rec-200',
              evaluation_id: 'eval-200',
              header: {{ report_title: 'Informe final' }},
              exports: {{ report_json: exportedJson }},
              media: {{
                video_ref: 'gs://bucket/media-video.mp4',
                poster_frame_ref: 'gs://bucket/media-poster.png',
                duration_ms: 65432,
                mime_type: 'video/mp4',
                recording_id: 'rec-200',
              }},
            }};
            (async () => {{
              const payload = await buildCommunicationFinalResultPayload(report, {{ rootElement: {{ id: 'reportPlaceholderRoot' }} }});
              process.stdout.write(JSON.stringify({{ payload, exportedHtml, exportedJson, exportedSnapshot }}));
            }})();
            """
        )
        completed = subprocess.run(
            ['node', '-e', script],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_final_result_reuses_report_exports_and_media_refs(self) -> None:
        output = self._run_exports_harness()
        payload = output['payload']

        self.assertEqual(payload['summary_html'], output['exportedHtml'])
        self.assertEqual(payload['payloadjson'], output['exportedJson'])
        self.assertEqual(payload['snapshot_png_dataurl'], output['exportedSnapshot'])
        self.assertEqual(payload['video_ref'], 'gs://bucket/media-video.mp4')
        self.assertEqual(payload['poster_frame_ref'], 'gs://bucket/media-poster.png')
        self.assertEqual(payload['duration_ms'], 65432)
        self.assertEqual(payload['media']['video_ref'], payload['video_ref'])
        self.assertEqual(payload['media']['poster_frame_ref'], payload['poster_frame_ref'])
        self.assertEqual(payload['media']['duration_ms'], payload['duration_ms'])
        self.assertEqual(payload['recording_id'], 'rec-200')
        self.assertEqual(payload['attempt_id'], 'attempt-200')
        self.assertEqual(payload['evaluation_id'], 'eval-200')

    def test_source_still_exposes_export_helpers_used_by_final_result(self) -> None:
        for marker in [
            'async function exportReportJson()',
            'async function exportReportHtml()',
            'async function exportReportPng()',
            'serializeCommunicationReportToHtml(state.report.payload)',
            'captureCommunicationReportPngDataUrl(state.report.payload)',
            'buildCommunicationFinalResultPayload',
            'summary_html',
            'snapshot_png_dataurl',
            'payloadjson',
        ]:
            self.assertIn(marker, self.source)


if __name__ == '__main__':
    unittest.main()
