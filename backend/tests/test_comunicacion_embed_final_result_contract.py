from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
from pathlib import Path

from backend.comunicacion.final_result_models import (
    CommunicationFinalResultEnvelopeV1,
    CommunicationFinalResultSavedAckV1,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_JS = REPO_ROOT / 'backend' / 'comunicacion_app' / 'app.js'


class ComunicacionEmbedFinalResultContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app_source = APP_JS.read_text(encoding='utf-8')

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
            'readEmbedModeFromUrl',
            'readEmbedOriginFromUrl',
            'isEmbeddedRuntime',
            'detectEmbedMode',
            'buildCommunicationEmbedEnvelope',
            'stableStringifyForHash',
            'simpleHashString',
            'deriveCommunicationFinalPayloadHash',
            'buildCommunicationFinalCorrelationId',
            'registerPendingCommunicationFinalAck',
            'isAllowedParentOrigin',
            'readCommunicationAckComparableIds',
            'handleCommunicationEmbeddedSaveAck',
            'buildCommunicationFinalResultPayload',
            'buildCommunicationFinalAvailabilityPayload',
            'emitCommunicationFinalResultLifecycle',
        ]
        extracted = '\n\n'.join(self._extract_function_source(self.app_source, name) for name in functions)
        script = textwrap.dedent(
            f"""
            const EMBED_MESSAGE_VERSION = 1;
            const EMBED_NAMESPACE = 'gestionce.simulator';
            const state = {{
              session: {{
                session_id: 'sess-comm-001',
                context_id: 'ctx-comm-001',
                public_slug: 'comunicacion',
                user_id: 'user-123',
              }},
              attempt: {{
                attempt_id: 'attempt-123',
              }},
              evaluation: {{
                evaluation_id: 'eval-comm-123',
              }},
              report: {{
                payload: null,
              }},
              final_delivery: {{
                status: 'idle',
                last_error: null,
                pending_ack: null,
                last_payload: null,
                ack_meta: null,
              }},
            }};
            const sentEnvelopes = [];
            const renderEvents = [];
            function renderApp() {{
              renderEvents.push(state.final_delivery.status);
            }}
            const window = {{
              location: {{
                search: '?embed=1&parent_origin=https%3A%2F%2Facademia.gestionce.com',
              }},
              parent: {{
                postMessage(envelope) {{
                  sentEnvelopes.push(envelope);
                }},
              }},
              CommunicationReportView: {{
                serializeCommunicationReportToHtml(report) {{
                  return `<article><h1>${{report.header.report_title}}</h1></article>`;
                }},
                async captureCommunicationReportPngDataUrl(report, options) {{
                  if (!options || !options.rootElement || options.rootElement.id !== 'reportPlaceholderRoot') {{
                    throw new Error('captureCommunicationReportPngDataUrl debe recibir el root visible del informe');
                  }}
                  return 'data:image/png;base64,Y29tdW5pY2FjaW9u';
                }},
                renderCommunicationReport() {{}},
                renderCommunicationReportPlaceholder() {{}},
              }},
              addEventListener() {{}},
            }};
            globalThis.window = window;
            globalThis.URLSearchParams = URLSearchParams;
            globalThis.global = window;
            const console = {{
              info() {{}},
              warn() {{}},
              log(value) {{ process.stdout.write(String(value) + '\\n'); }},
            }};
            {extracted}
            const report = {{
              evaluation_id: 'eval-comm-123',
              recording_id: 'rec-123',
              attempt_id: 'attempt-123',
              header: {{
                report_title: 'Evaluación de tu comunicación oral',
              }},
              media: {{
                video_ref: 'gs://bucket/video.mp4',
                poster_frame_ref: 'gs://bucket/poster.png',
                duration_ms: 93000,
                mime_type: 'video/mp4',
                recording_id: 'rec-123',
              }},
              exports: {{
                report_json: {{ ok: true, blocks: 3 }},
              }},
            }};
            (async () => {{
              const payload = await buildCommunicationFinalResultPayload(report, {{ rootElement: {{ id: 'reportPlaceholderRoot' }} }});
              const envelopePayload = buildCommunicationEmbedEnvelope('final_result', payload, {{ correlationId: buildCommunicationFinalCorrelationId(payload) }});
              await emitCommunicationFinalResultLifecycle(report, {{ rootElement: {{ id: 'reportPlaceholderRoot' }} }});
              const pendingAfterEmit = state.final_delivery.pending_ack;
              const emittedEnvelope = sentEnvelopes[sentEnvelopes.length - 1];
              const emittedTypes = sentEnvelopes.map((entry) => entry.type);
              const ackAccepted = handleCommunicationEmbeddedSaveAck({{
                ns: EMBED_NAMESPACE,
                v: EMBED_MESSAGE_VERSION,
                type: 'final_result_saved',
                payload: {{
                  status: 'ok',
                  session_id: payload.session_id,
                  activityid: payload.activityid,
                  evaluation_id: payload.evaluation_id,
                  payload_hash: payload.payload_hash,
                  correlation_id: emittedEnvelope.correlation_id,
                }},
              }}, {{ origin: 'https://academia.gestionce.com' }});
              const duplicateAckAccepted = handleCommunicationEmbeddedSaveAck({{
                ns: EMBED_NAMESPACE,
                v: EMBED_MESSAGE_VERSION,
                type: 'final_result_saved',
                payload: {{
                  status: 'ok',
                  session_id: payload.session_id,
                  activityid: payload.activityid,
                  evaluation_id: payload.evaluation_id,
                  payload_hash: payload.payload_hash,
                  correlation_id: emittedEnvelope.correlation_id,
                }},
              }}, {{ origin: 'https://academia.gestionce.com' }});
              state.final_delivery.pending_ack = {{ ...pendingAfterEmit, pending_ack: true, ack_confirmed: false }};
              const ackWithoutPayloadHashWithEvaluationAccepted = handleCommunicationEmbeddedSaveAck({{
                ns: EMBED_NAMESPACE,
                v: EMBED_MESSAGE_VERSION,
                type: 'final_result_saved',
                payload: {{
                  status: 'ok',
                  session_id: payload.session_id,
                  activityid: payload.activityid,
                  evaluation_id: payload.evaluation_id,
                }},
              }}, {{ origin: 'https://academia.gestionce.com' }});
              state.final_delivery.pending_ack = {{ ...pendingAfterEmit, pending_ack: true, ack_confirmed: false }};
              const ackWithoutPayloadHashWithCorrelationAccepted = handleCommunicationEmbeddedSaveAck({{
                ns: EMBED_NAMESPACE,
                v: EMBED_MESSAGE_VERSION,
                type: 'final_result_saved',
                payload: {{
                  status: 'ok',
                  session_id: payload.session_id,
                  activityid: payload.activityid,
                  correlation_id: emittedEnvelope.correlation_id,
                }},
              }}, {{ origin: 'https://academia.gestionce.com' }});
              state.final_delivery.pending_ack = {{ ...pendingAfterEmit, pending_ack: true, ack_confirmed: false }};
              const wrongOriginAccepted = handleCommunicationEmbeddedSaveAck({{
                ns: EMBED_NAMESPACE,
                v: EMBED_MESSAGE_VERSION,
                type: 'final_result_saved',
                payload: {{
                  status: 'ok',
                  session_id: payload.session_id,
                  activityid: payload.activityid,
                  evaluation_id: payload.evaluation_id,
                  payload_hash: payload.payload_hash,
                  correlation_id: emittedEnvelope.correlation_id,
                }},
              }}, {{ origin: 'https://otro.example.com' }});
              console.log(JSON.stringify({{
                payload,
                envelopePayload,
                emittedEnvelope,
                emittedTypes,
                pendingAfterEmit,
                ackAccepted,
                duplicateAckAccepted,
                ackWithoutPayloadHashWithEvaluationAccepted,
                ackWithoutPayloadHashWithCorrelationAccepted,
                wrongOriginAccepted,
                finalStatus: state.final_delivery.status,
                ackMeta: state.final_delivery.ack_meta,
                renderEvents,
              }}));
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

    def test_build_and_ack_final_result_payload(self) -> None:
        output = self._run_node_contract_harness()
        payload = output['payload']
        emitted_envelope = output['emittedEnvelope']
        pending = output['pendingAfterEmit']

        self.assertEqual(payload['schema_version'], 'comunicacion_final_result.v1')
        self.assertEqual(payload['activity_type'], 'comunicacion')
        self.assertEqual(payload['session_id'], 'sess-comm-001')
        self.assertEqual(payload['attempt_id'], 'attempt-123')
        self.assertEqual(payload['recording_id'], 'rec-123')
        self.assertEqual(payload['evaluation_id'], 'eval-comm-123')
        self.assertEqual(payload['public_slug'], 'comunicacion')
        self.assertEqual(payload['video_ref'], 'gs://bucket/video.mp4')
        self.assertEqual(payload['media']['mime_type'], 'video/mp4')
        self.assertEqual(payload['summary_html'], '<article><h1>Evaluación de tu comunicación oral</h1></article>')
        self.assertEqual(payload['snapshot_png_dataurl'], 'data:image/png;base64,Y29tdW5pY2FjaW9u')
        self.assertEqual(payload['payloadjson'], {'ok': True, 'blocks': 3})
        self.assertEqual(payload['payload_hash'][:6], 'fnv1a:')

        self.assertEqual(output['emittedTypes'], ['final_result_available', 'final_result'])
        self.assertEqual(emitted_envelope['ns'], 'gestionce.simulator')
        self.assertEqual(emitted_envelope['v'], 1)
        self.assertEqual(emitted_envelope['type'], 'final_result')
        self.assertEqual(emitted_envelope['payload']['payload_hash'], payload['payload_hash'])
        self.assertIn(payload['payload_hash'], emitted_envelope['correlation_id'])
        self.assertEqual(pending['correlation_id'], emitted_envelope['correlation_id'])
        self.assertEqual(pending['payload_hash'], payload['payload_hash'])

        self.assertTrue(output['ackAccepted'])
        self.assertFalse(output['duplicateAckAccepted'])
        self.assertFalse(output['ackWithoutPayloadHashWithEvaluationAccepted'])
        self.assertFalse(output['ackWithoutPayloadHashWithCorrelationAccepted'])
        self.assertFalse(output['wrongOriginAccepted'])
        self.assertEqual(output['finalStatus'], 'ack_received')
        self.assertEqual(output['ackMeta']['payload_hash'], payload['payload_hash'])
        self.assertIn('sending', output['renderEvents'])
        self.assertIn('ack_received', output['renderEvents'])

    def test_embed_requires_parent_origin_configuration(self) -> None:
        functions = [
            'readEmbedModeFromUrl',
            'readEmbedOriginFromUrl',
            'isEmbeddedRuntime',
            'detectEmbedMode',
            'buildCommunicationEmbedEnvelope',
            'stableStringifyForHash',
            'simpleHashString',
            'deriveCommunicationFinalPayloadHash',
            'buildCommunicationFinalResultPayload',
            'buildCommunicationFinalAvailabilityPayload',
            'emitCommunicationFinalResultLifecycle',
        ]
        extracted = '\n\n'.join(self._extract_function_source(self.app_source, name) for name in functions)
        script = textwrap.dedent(
            f"""
            const EMBED_MESSAGE_VERSION = 1;
            const EMBED_NAMESPACE = 'gestionce.simulator';
            const state = {{
              session: {{ session_id: 'sess-comm-001', context_id: 'ctx-comm-001', public_slug: 'comunicacion', user_id: 'user-123' }},
              attempt: {{ attempt_id: 'attempt-123' }},
              evaluation: {{ evaluation_id: 'eval-comm-123' }},
              final_delivery: {{ status: 'idle', last_error: null, pending_ack: null, last_payload: null, ack_meta: null }},
            }};
            const sentEnvelopes = [];
            function renderApp() {{}}
            const window = {{
              location: {{ search: '?embed=1' }},
              parent: {{ postMessage(envelope) {{ sentEnvelopes.push(envelope); }} }},
              CommunicationReportView: {{
                serializeCommunicationReportToHtml() {{ return '<article>ok</article>'; }},
                async captureCommunicationReportPngDataUrl() {{ return 'data:image/png;base64,Y29tdW5pY2FjaW9u'; }},
              }},
            }};
            globalThis.window = window;
            globalThis.URLSearchParams = URLSearchParams;
            globalThis.global = window;
            {extracted}
            const report = {{
              evaluation_id: 'eval-comm-123',
              recording_id: 'rec-123',
              attempt_id: 'attempt-123',
              header: {{ report_title: 'Evaluación de tu comunicación oral' }},
              media: {{ video_ref: 'gs://bucket/video.mp4', poster_frame_ref: 'gs://bucket/poster.png', duration_ms: 93000, mime_type: 'video/mp4' }},
              exports: {{ report_json: {{ ok: true }} }},
            }};
            (async () => {{
              await emitCommunicationFinalResultLifecycle(report, {{ rootElement: {{ id: 'reportPlaceholderRoot' }} }});
              process.stdout.write(JSON.stringify({{
                sentCount: sentEnvelopes.length,
                status: state.final_delivery.status,
                lastError: state.final_delivery.last_error,
              }}));
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
        output = json.loads(completed.stdout)
        self.assertEqual(output['sentCount'], 0)
        self.assertEqual(output['status'], 'error')
        self.assertEqual(output['lastError'], 'embed_parent_origin_missing')

    def test_pydantic_models_accept_valid_final_result_contract(self) -> None:
        output = self._run_node_contract_harness()
        envelope = CommunicationFinalResultEnvelopeV1.model_validate(output['emittedEnvelope'])
        self.assertEqual(envelope.type, 'final_result')
        self.assertEqual(envelope.payload.schema_version, 'comunicacion_final_result.v1')
        self.assertEqual(envelope.payload.media.video_ref, 'gs://bucket/video.mp4')

        ack = CommunicationFinalResultSavedAckV1.model_validate(
            {
                'ns': 'gestionce.simulator',
                'v': 1,
                'type': 'final_result_saved',
                'payload': {
                    'status': 'ok',
                    'session_id': envelope.payload.session_id,
                    'activityid': envelope.payload.activityid,
                    'evaluation_id': envelope.payload.evaluation_id,
                    'payload_hash': envelope.payload.payload_hash,
                    'correlation_id': envelope.correlation_id,
                },
            }
        )
        self.assertEqual(ack.type, 'final_result_saved')
        self.assertEqual(ack.payload['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
