from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
from pathlib import Path

from backend.comunicacion.final_result_models import CommunicationFinalResultPayloadV1

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_JS = REPO_ROOT / 'backend' / 'comunicacion_app' / 'app.js'


class CommunicationFinalResultContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app_source = APP_JS.read_text(encoding='utf-8')

    def _extract_function_source(self, name: str) -> str:
        source = self.app_source
        async_marker = f'async function {name}'
        marker = async_marker if async_marker in source else f'function {name}'
        start = source.find(marker)
        self.assertNotEqual(start, -1, f'No se encontró {name} en app.js')
        params_end = source.find(')', start)
        self.assertNotEqual(params_end, -1)
        brace_start = source.find('{', params_end)
        self.assertNotEqual(brace_start, -1)

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

    def _build_payload(self, snapshot_data_url: str = 'data:image/png;base64,c25hcHNob3Q=') -> dict:
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
              session: {{
                session_id: 'sess-100',
                context_id: 'ctx-100',
                public_slug: 'comunicacion',
                user_id: 'user-100',
              }},
              attempt: {{ attempt_id: 'attempt-100' }},
              evaluation: {{ evaluation_id: 'eval-100' }},
            }};
            const window = {{
              CommunicationReportView: {{
                serializeCommunicationReportToHtml(report) {{
                  return `<section data-report="html"><h1>${{report.header.report_title}}</h1><p>${{report.header.summary}}</p></section>`;
                }},
                async captureCommunicationReportPngDataUrl() {{
                  return {json.dumps(snapshot_data_url)};
                }},
              }},
            }};
            globalThis.window = window;
            globalThis.global = window;
            {extracted}
            const report = {{
              attempt_id: 'attempt-100',
              recording_id: 'rec-100',
              evaluation_id: 'eval-100',
              header: {{
                report_title: 'Evaluación final de comunicación',
                summary: 'Resumen ejecutivo',
              }},
              exports: {{
                report_json: {{ exported: true, sections: ['intro', 'recommendations'] }},
              }},
              media: {{
                video_ref: 'gs://bucket/final-video.mp4',
                poster_frame_ref: 'gs://bucket/final-poster.png',
                duration_ms: 87000,
                mime_type: 'video/mp4',
                recording_id: 'rec-100',
              }},
            }};
            (async () => {{
              const payload = await buildCommunicationFinalResultPayload(report, {{ rootElement: {{ id: 'reportPlaceholderRoot' }} }});
              process.stdout.write(JSON.stringify(payload));
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

    def test_final_payload_shape_preserves_required_artifacts(self) -> None:
        payload = self._build_payload()
        validated = CommunicationFinalResultPayloadV1.model_validate(payload)

        self.assertEqual(validated.activity_type, 'comunicacion')
        self.assertEqual(validated.title, 'Evaluación final de comunicación')
        self.assertEqual(validated.activityid, 'comunicacion')
        self.assertEqual(validated.session_id, 'sess-100')
        self.assertEqual(validated.attempt_id, 'attempt-100')
        self.assertEqual(validated.recording_id, 'rec-100')
        self.assertEqual(validated.evaluation_id, 'eval-100')
        self.assertEqual(validated.summary_html, '<section data-report="html"><h1>Evaluación final de comunicación</h1><p>Resumen ejecutivo</p></section>')
        self.assertEqual(validated.snapshot_png_dataurl, 'data:image/png;base64,c25hcHNob3Q=')
        self.assertEqual(validated.payloadjson, {'exported': True, 'sections': ['intro', 'recommendations']})
        self.assertEqual(validated.video_ref, 'gs://bucket/final-video.mp4')
        self.assertEqual(validated.poster_frame_ref, 'gs://bucket/final-poster.png')
        self.assertEqual(validated.duration_ms, 87000)
        self.assertEqual(validated.media.video_ref, validated.video_ref)
        self.assertEqual(validated.media.poster_frame_ref, validated.poster_frame_ref)
        self.assertEqual(validated.media.duration_ms, validated.duration_ms)
        self.assertTrue(validated.payload_hash.startswith('fnv1a:'))

    def test_payload_hash_changes_when_preserved_artifacts_change(self) -> None:
        first = self._build_payload(snapshot_data_url='data:image/png;base64,c25hcHNob3Q=')
        second = self._build_payload(snapshot_data_url='data:image/png;base64,b3RoZXItc25hcA==')
        self.assertNotEqual(first['payload_hash'], second['payload_hash'])


if __name__ == '__main__':
    unittest.main()
