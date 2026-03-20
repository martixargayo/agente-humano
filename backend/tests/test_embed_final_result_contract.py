from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import app

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_JS = REPO_ROOT / 'backend' / 'interfaz_usuario_app' / 'app.js'
FEEDBACK_JS = REPO_ROOT / 'backend' / 'interfaz_usuario_app' / 'feedback_report_view.js'


class EmbedFinalResultContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)
        self.app_source = APP_JS.read_text(encoding='utf-8')
        self.feedback_source = FEEDBACK_JS.read_text(encoding='utf-8')

    def _extract_function_source(self, source: str, name: str) -> str:
        async_marker = f'async function {name}'
        marker = async_marker if async_marker in source else f'function {name}'
        start = source.find(marker)
        self.assertNotEqual(start, -1, f'No se encontró {name} en app.js')
        params_end = source.find(')', start)
        self.assertNotEqual(params_end, -1, f'No se encontró cierre de parámetros para {name}')
        brace_start = source.find('{', params_end)
        self.assertNotEqual(brace_start, -1, f'No se encontró apertura de bloque para {name}')

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

        self.fail(f'No se pudo extraer el cuerpo completo de {name}')

    def _run_node_contract_harness(self) -> dict:
        functions = [
            'transparentFallbackPngDataUrl',
            'deriveFinalResultTitle',
            'deriveFinalResultActivityId',
            'buildEmbedEnvelope',
            'buildFinalResultPayload',
        ]
        extracted = '\n\n'.join(self._extract_function_source(self.app_source, name) for name in functions)
        script = textwrap.dedent(
            f"""
            const EMBED_MESSAGE_VERSION = 1;
            const EMBED_NAMESPACE = 'gestionce.simulator';
            let feedbackEvaluationId = 'eval-123';
            const correlation = {{
              session_id: 'sess-001',
              conversation_id: 'conv-001',
              context_id: 'ctx-001',
              public_slug: 'negociacion',
              trace_count: 14,
              bootstrapped_at: '2026-03-20T10:00:00.000Z',
            }};
            function getSessionCorrelationMeta() {{
              return correlation;
            }}
            const window = {{
              FeedbackReportView: {{
                serializeReportToHtml(report) {{
                  return `<html><body><h1>${{report.header.report_title}}</h1></body></html>`;
                }},
                async captureReportPngDataUrl() {{
                  return 'data:image/png;base64,ZmFrZS1wbmc=';
                }},
              }},
            }};
            {extracted}
            const report = {{
              schema_version: 'ui_feedback_report.v1',
              evaluation_id: 'eval-123',
              header: {{
                report_title: 'Evaluación de tu desempeño',
                activity_name: 'Compra de un Mustang clásico',
                score_global_100: 87,
                stars_0_5: 4.4,
                interaction_outcome: 'agreement_reached',
                summary_2_3_lines: 'Resumen breve del informe.',
              }},
              block_cards: [],
              trajectory_chart: [],
              key_moments: {{
                best_moment: {{}},
                most_delicate_moment: {{}},
                turning_point: {{}},
              }},
              recommendations: {{ items: [] }},
              provenance: {{
                evaluation_id: 'eval-123',
                bundle_hash: 'bundle',
                core_input_hash: 'core-in',
                trajectory_input_hash: 'traj-in',
                core_output_hash: 'core-out',
                trajectory_output_hash: 'traj-out',
                core_model: 'gpt',
                trajectory_model: 'gpt',
                core_prompt_version: 'v1',
                trajectory_prompt_version: 'v1',
                flow_id: 'negociacion',
                context_id: 'ctx-001',
                context_version: '2026-03',
              }},
            }};
            (async () => {{
              const payload = await buildFinalResultPayload(report, {{ reason: 'report-fetched' }});
              const envelope = buildEmbedEnvelope('final_result', payload);
              console.log(JSON.stringify({{ payload, envelope }}));
            }})().catch((err) => {{
              console.error(err);
              process.exit(1);
            }});
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

    def test_build_final_result_payload_matches_moodle_contract(self) -> None:
        output = self._run_node_contract_harness()
        payload = output['payload']
        envelope = output['envelope']

        self.assertEqual(payload['title'], 'Evaluación de tu desempeño')
        self.assertEqual(payload['activityid'], 'negociacion')
        self.assertEqual(payload['session_id'], 'sess-001')
        self.assertEqual(payload['conversation_id'], 'conv-001')
        self.assertEqual(payload['context_id'], 'ctx-001')
        self.assertEqual(payload['public_slug'], 'negociacion')
        self.assertEqual(payload['trace_count'], 14)
        self.assertEqual(payload['summary_html'], '<html><body><h1>Evaluación de tu desempeño</h1></body></html>')
        self.assertEqual(payload['payloadjson']['schema_version'], 'ui_feedback_report.v1')
        self.assertEqual(payload['report_json']['header']['activity_name'], 'Compra de un Mustang clásico')
        self.assertEqual(payload['report_html'], payload['summary_html'])
        self.assertEqual(payload['snapshot_png_dataurl'], 'data:image/png;base64,ZmFrZS1wbmc=')
        self.assertEqual(payload['reason'], 'report-fetched')
        self.assertEqual(payload['available_exports'], ['html', 'json', 'png'])
        self.assertRegex(payload['generated_at'], r'^\d{4}-\d{2}-\d{2}T')

        self.assertEqual(envelope['ns'], 'gestionce.simulator')
        self.assertEqual(envelope['v'], 1)
        self.assertEqual(envelope['type'], 'final_result')
        self.assertEqual(envelope['session_id'], 'sess-001')
        self.assertEqual(envelope['conversation_id'], 'conv-001')
        self.assertEqual(envelope['context_id'], 'ctx-001')
        self.assertEqual(envelope['public_slug'], 'negociacion')
        self.assertIn('payload', envelope)
        self.assertEqual(envelope['payload']['activityid'], 'negociacion')

    def test_public_assets_expose_new_embed_contract_and_keep_manual_exports(self) -> None:
        app_js = self.client.get('/interfaz_usuario/app.js')
        feedback_js = self.client.get('/interfaz_usuario/feedback_report_view.js')

        self.assertEqual(app_js.status_code, 200)
        self.assertIn("title: deriveFinalResultTitle(report)", app_js.text)
        self.assertIn("activityid: deriveFinalResultActivityId(report, correlation)", app_js.text)
        self.assertIn("session_id: correlation?.session_id || null", app_js.text)
        self.assertIn("snapshot_png_dataurl: snapshotPngDataUrl", app_js.text)
        self.assertIn("generated_at: new Date().toISOString()", app_js.text)
        self.assertIn("window.parent.postMessage(buildEmbedEnvelope(type, payload), PARENT_EMBED_ORIGIN)", app_js.text)
        self.assertNotIn("postMessage(buildEmbedEnvelope(type, payload), '*')", app_js.text)
        self.assertIn("emitEmbedMessage('final_result_available'", app_js.text)
        self.assertIn("emitEmbedMessage('final_result', payload)", app_js.text)

        self.assertEqual(feedback_js.status_code, 200)
        self.assertIn('async function captureReportPngDataUrl(report, options = {})', feedback_js.text)
        self.assertIn('captureReportPngDataUrl,', feedback_js.text)
        self.assertIn('async function downloadReportPng(report, options = {})', feedback_js.text)
        self.assertIn("options.filename || 'evaluacion-desempeno.html'", feedback_js.text)
        self.assertIn("options.filename || 'evaluacion-desempeno.json'", feedback_js.text)
        self.assertIn("options.filename || 'evaluacion-desempeno.png'", feedback_js.text)


if __name__ == '__main__':
    unittest.main()
