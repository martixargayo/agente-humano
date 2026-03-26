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

    def test_happy_path_uses_dom_capture_as_primary_strategy(self) -> None:
        output = self._run_harness(from_dom_mode='ok')
        self.assertEqual(output['value'], 'data:image/png;base64,RE9NX1NOT1Q=')
        self.assertEqual(output['calls'], [['fromDom']])

    def test_fallback_is_used_when_dom_capture_fails(self) -> None:
        output = self._run_harness(from_dom_mode='throw')
        self.assertEqual(output['value'], 'data:image/png;base64,RkFMTEJBQ0s=')
        self.assertEqual(output['calls'][0], ['fromDom'])
        self.assertIn(['fallback'], output['calls'])


if __name__ == '__main__':
    unittest.main()
