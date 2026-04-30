from __future__ import annotations

import json
import subprocess
import textwrap
import unittest
from pathlib import Path


class InterfazUsuarioKeyboardProxyRuntimeTests(unittest.TestCase):
    def test_parent_origin_resolution_uses_allowlist_without_wildcard(self) -> None:
        app_js = Path("backend/interfaz_usuario_app/app.js").read_text(encoding="utf-8")
        node_script = textwrap.dedent(
            f"""
            const src = {json.dumps(app_js)};

            const constantsStart = src.indexOf('const DEFAULT_PARENT_EMBED_ORIGIN');
            const constantsEnd = src.indexOf('const EMBED_NAMESPACE');
            if (constantsStart < 0 || constantsEnd < 0 || constantsEnd <= constantsStart) throw new Error('parent origin constants block missing');
            const constantsBlock = src
              .slice(constantsStart, constantsEnd)
              .replace('const DEFAULT_PARENT_EMBED_ORIGIN', 'globalThis.DEFAULT_PARENT_EMBED_ORIGIN')
              .replace('const ALLOWED_PARENT_EMBED_ORIGINS', 'globalThis.ALLOWED_PARENT_EMBED_ORIGINS');

            const fnStart = src.indexOf('function normalizeOriginCandidate');
            const fnEnd = src.indexOf('const InputMode =');
            if (fnStart < 0 || fnEnd < 0 || fnEnd <= fnStart) throw new Error('parent origin function block missing');
            const fnBlock = src.slice(fnStart, fnEnd);

            function boot(href) {{
              globalThis.window = {{ location: {{ href }} }};
              eval(constantsBlock);
              eval(fnBlock);
              return {{
                resolved: resolveParentEmbedOrigin(),
                normalizedBad: normalizeOriginCandidate('javascript:alert(1)'),
                allowed: Array.from(ALLOWED_PARENT_EMBED_ORIGINS),
              }};
            }}

            const prod = boot('https://app.local/interfaz_usuario?embed=1&parent_origin=https%3A%2F%2Facademia.gestionce.com');
            if (prod.resolved !== 'https://academia.gestionce.com') throw new Error('prod origin not resolved');

            const staging = boot('https://app.local/interfaz_usuario?embed=1&parent_origin=https%3A%2F%2Fstaging.academia.gestionce.com');
            if (staging.resolved !== 'https://staging.academia.gestionce.com') throw new Error('staging origin not resolved');

            const notAllowed = boot('https://app.local/interfaz_usuario?embed=1&parent_origin=https%3A%2F%2Fevil.example');
            if (notAllowed.resolved !== 'https://academia.gestionce.com') throw new Error('non-allowed origin should fallback');

            const malformed = boot('https://app.local/interfaz_usuario?embed=1&parent_origin=::::');
            if (malformed.resolved !== 'https://academia.gestionce.com') throw new Error('malformed origin should fallback');

            const absent = boot('https://app.local/interfaz_usuario?embed=1');
            if (absent.resolved !== 'https://academia.gestionce.com') throw new Error('absent origin should fallback');

            if (prod.allowed.includes('*')) throw new Error('wildcard must not be allowed');
            if (prod.normalizedBad !== null) throw new Error('malicious protocol must be rejected');
            console.log('ok');
            """
        )
        result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise AssertionError(f"Node origin resolution test failed:\\nSTDOUT:\\n{result.stdout}\\nSTDERR:\\n{result.stderr}")
        self.assertIn("ok", result.stdout)

    def test_keyboard_proxy_runtime_contract_and_guards(self) -> None:
        app_js = Path("backend/interfaz_usuario_app/app.js").read_text(encoding="utf-8")
        node_script = textwrap.dedent(
            f"""
            const fs = require('fs');
            const src = {json.dumps(app_js)};

            const fnStart = src.indexOf('function isAllowedParentOrigin');
            const fnEnd = src.indexOf('function emitParentEmbedError');
            if (fnStart < 0 || fnEnd < 0 || fnEnd <= fnStart) throw new Error('keyboard proxy function block not found');
            const fnBlock = src.slice(fnStart, fnEnd);

            globalThis.EMBED_NAMESPACE = 'gestionce.simulator';
            globalThis.EMBED_MESSAGE_VERSION = 1;
            globalThis.EMBED_KEYBOARD_PROXY_TTL_MS = 10_000;
            globalThis.EMBED_KEYBOARD_PROXY_MAX_SEEN = 100;
            globalThis.PARENT_EMBED_ORIGIN = 'https://academia.gestionce.com';
            globalThis.turnInFlight = false;
            globalThis.voiceTurnInFlight = false;
            globalThis.busy = false;
            globalThis.InputMode = {{ WRITE: 'write', TALK: 'talk' }};
            globalThis.currentInputMode = globalThis.InputMode.WRITE;
            globalThis.ui = {{
              textInput: {{ value: '', disabled: false }},
              finishTurnBtn: {{ disabled: false }},
            }};
            globalThis.seenKeyboardProxyCorrelation = new Map();
            globalThis.sendCalls = 0;
            globalThis.finishCalls = 0;
            globalThis.handleSend = function handleSend() {{ globalThis.sendCalls += 1; }};
            globalThis.handleFinishTurn = function handleFinishTurn() {{ globalThis.finishCalls += 1; }};
            globalThis.getActiveSessionBusyState = function getActiveSessionBusyState() {{
              return globalThis.busy ? {{ busy: true }} : null;
            }};
            eval(fnBlock);

            function basePayload(overrides = {{}}) {{
              return {{
                key: 'Enter',
                code: 'Enter',
                altKey: false,
                ctrlKey: false,
                metaKey: false,
                shiftKey: false,
                repeat: false,
                sent_at: Date.now(),
                correlation_id: 'kbd-1',
                ...overrides,
              }};
            }}

            function runCase(name, fn) {{
              const out = fn();
              if (!out) throw new Error(`failed case: ${{name}}`);
            }}

            runCase('valid write mode sends exactly once', () => {{
              currentInputMode = InputMode.WRITE;
              ui.textInput.value = 'hola';
              const accepted = handleEmbeddedKeyboardProxy({{
                origin: PARENT_EMBED_ORIGIN,
                data: {{
                  namespace: EMBED_NAMESPACE,
                  version: 1,
                  type: 'keyboard_proxy',
                  payload: basePayload({{ correlation_id: 'kbd-ok-1' }}),
                }},
              }});
              return accepted === true && sendCalls === 1 && finishCalls === 0;
            }});

            runCase('invalid origin ignored', () => {{
              const before = sendCalls;
              const accepted = handleEmbeddedKeyboardProxy({{
                origin: 'https://evil.example',
                data: {{
                  namespace: EMBED_NAMESPACE,
                  version: 1,
                  type: 'keyboard_proxy',
                  payload: basePayload({{ correlation_id: 'kbd-bad-origin' }}),
                }},
              }});
              return accepted === false && sendCalls === before;
            }});

            const invalidEnvelopeCases = [
              ['namespace', {{ namespace: 'wrong', version: 1, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-ns' }}) }}],
              ['version', {{ namespace: EMBED_NAMESPACE, version: 2, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-ver' }}) }}],
              ['type', {{ namespace: EMBED_NAMESPACE, version: 1, type: 'other', payload: basePayload({{ correlation_id: 'kbd-type' }}) }}],
            ];
            invalidEnvelopeCases.forEach(([_, data]) => {{
              const before = sendCalls;
              const accepted = handleEmbeddedKeyboardProxy({{ origin: PARENT_EMBED_ORIGIN, data }});
              if (!(accepted === false && sendCalls === before)) throw new Error('invalid envelope case failed');
            }});

            const invalidPayloads = [
              null,
              {{ key: 'Space', code: 'Enter', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, sent_at: Date.now(), correlation_id: 'kbd-space' }},
              {{ key: 'Enter', code: 'KeyA', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, sent_at: Date.now(), correlation_id: 'kbd-code' }},
              {{ key: 'Enter', code: 'Enter', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, repeat: true, sent_at: Date.now(), correlation_id: 'kbd-repeat' }},
              {{ key: 'Enter', code: 'Enter', altKey: false, ctrlKey: true, metaKey: false, shiftKey: false, repeat: false, sent_at: Date.now(), correlation_id: 'kbd-ctrl' }},
              {{ key: 'Enter', code: 'Enter', altKey: false, ctrlKey: false, metaKey: true, shiftKey: false, repeat: false, sent_at: Date.now(), correlation_id: 'kbd-meta' }},
              {{ key: 'Enter', code: 'Enter', altKey: true, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, sent_at: Date.now(), correlation_id: 'kbd-alt' }},
              {{ key: 'Enter', code: 'Enter', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, sent_at: Date.now() - 20_000, correlation_id: 'kbd-stale' }},
              {{ key: 'Enter', code: 'Enter', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, sent_at: 'bad-ts', correlation_id: 'kbd-bad-ts' }},
              {{ key: 'Enter', code: 'Enter', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, sent_at: Date.now(), correlation_id: '' }},
              {{ key: 'Enter', code: 'Enter', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, sent_at: Date.now() }},
            ];
            invalidPayloads.forEach((payload, idx) => {{
              const before = sendCalls;
              const accepted = handleEmbeddedKeyboardProxy({{
                origin: PARENT_EMBED_ORIGIN,
                data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload }},
              }});
              if (accepted !== true || sendCalls !== before) throw new Error(`invalid payload failed at ${{idx}}`);
            }});

            runCase('duplicate correlation ignored', () => {{
              const before = sendCalls;
              const duplicatePayload = basePayload({{ correlation_id: 'kbd-dup' }});
              const first = handleEmbeddedKeyboardProxy({{
                origin: PARENT_EMBED_ORIGIN,
                data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: duplicatePayload }},
              }});
              const second = handleEmbeddedKeyboardProxy({{
                origin: PARENT_EMBED_ORIGIN,
                data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: duplicatePayload }},
              }});
              return first === true && second === true && sendCalls === before + 1;
            }});

            runCase('busy and inflight guards block sends', () => {{
              const before = sendCalls;
              busy = true;
              handleEmbeddedKeyboardProxy({{ origin: PARENT_EMBED_ORIGIN, data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-busy' }}) }} }});
              busy = false;
              turnInFlight = true;
              handleEmbeddedKeyboardProxy({{ origin: PARENT_EMBED_ORIGIN, data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-inflight' }}) }} }});
              turnInFlight = false;
              voiceTurnInFlight = true;
              handleEmbeddedKeyboardProxy({{ origin: PARENT_EMBED_ORIGIN, data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-voice-inflight' }}) }} }});
              voiceTurnInFlight = false;
              return sendCalls === before;
            }});

            runCase('write mode disabled/empty guards block sends', () => {{
              const before = sendCalls;
              currentInputMode = InputMode.WRITE;
              ui.textInput.value = '';
              ui.textInput.disabled = false;
              handleEmbeddedKeyboardProxy({{ origin: PARENT_EMBED_ORIGIN, data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-empty' }}) }} }});
              ui.textInput.value = 'hola';
              ui.textInput.disabled = true;
              handleEmbeddedKeyboardProxy({{ origin: PARENT_EMBED_ORIGIN, data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-disabled' }}) }} }});
              ui.textInput.disabled = false;
              return sendCalls === before;
            }});

            runCase('talk mode routes to finish action and respects disabled', () => {{
              const beforeSend = sendCalls;
              const beforeFinish = finishCalls;
              currentInputMode = InputMode.TALK;
              ui.finishTurnBtn.disabled = false;
              handleEmbeddedKeyboardProxy({{ origin: PARENT_EMBED_ORIGIN, data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-talk-ok' }}) }} }});
              ui.finishTurnBtn.disabled = true;
              handleEmbeddedKeyboardProxy({{ origin: PARENT_EMBED_ORIGIN, data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-talk-disabled' }}) }} }});
              ui.finishTurnBtn.disabled = false;
              return sendCalls === beforeSend && finishCalls === beforeFinish + 1;
            }});

            runCase('shift enter ignored and numpad enter accepted', () => {{
              currentInputMode = InputMode.WRITE;
              ui.textInput.value = 'texto';
              const before = sendCalls;
              handleEmbeddedKeyboardProxy({{ origin: PARENT_EMBED_ORIGIN, data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-shift', shiftKey: true }}) }} }});
              handleEmbeddedKeyboardProxy({{ origin: PARENT_EMBED_ORIGIN, data: {{ namespace: EMBED_NAMESPACE, version: 1, type: 'keyboard_proxy', payload: basePayload({{ correlation_id: 'kbd-numpad', code: 'NumpadEnter' }}) }} }});
              return sendCalls === before + 1;
            }});

            console.log('ok');
            """
        )
        result = subprocess.run(
            ["node", "-e", node_script],
            cwd=Path("."),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(f"Node runtime test failed:\\nSTDOUT:\\n{result.stdout}\\nSTDERR:\\n{result.stderr}")
        self.assertIn("ok", result.stdout)
