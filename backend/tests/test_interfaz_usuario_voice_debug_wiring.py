from __future__ import annotations

from pathlib import Path
import json
import subprocess
import textwrap


APP_JS = Path("backend/interfaz_usuario_app/app.js")


def test_voice_debug_helpers_and_flag_exist() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "const VOICE_DEBUG_STORAGE_KEY = 'gce_voice_debug';" in src
    assert "function isVoiceDebugEnabled()" in src
    assert "function voiceDebug(eventName, payload = {})" in src


def test_voice_debug_logs_lengths_not_full_transcript_text() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "transcript_len" in src
    assert "voiceDebug('stt_response'" in src
    assert "voiceDebug('pipeline_call'" in src
    # Ensure we do not explicitly log full transcript content key in debug payload.
    assert "transcript_text" not in src


def test_voice_debug_source_propagation_wiring() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "latestVoiceActionMeta = { source: 'keyboard_proxy'" in src
    assert "latestVoiceActionMeta = { source: 'button'" in src
    assert "latestVoiceActionMeta = { source: 'local_enter'" in src


def test_voice_debug_flag_runtime_off_and_on() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    start = src.index("const VOICE_DEBUG_STORAGE_KEY = 'gce_voice_debug';")
    end = src.index("function recordTurnPerf", start)
    block = src[start:end]
    script = textwrap.dedent(
        f"""
        const src = {json.dumps(block)};
        globalThis.window = {{ location: {{ search: '' }} }};
        globalThis.localStorage = {{
          store: new Map(),
          getItem(k) {{ return this.store.has(k) ? this.store.get(k) : null; }},
          setItem(k, v) {{ this.store.set(k, String(v)); }},
          removeItem(k) {{ this.store.delete(k); }},
        }};
        const events = [];
        const originalInfo = console.info;
        console.info = (...args) => events.push(args);
        eval(src);
        // debug off by default
        voiceDebug('off_case', {{ sample: 1 }});
        localStorage.setItem('gce_voice_debug', '1');
        voiceDebug('on_case', {{ sample: 2 }});
        console.info = originalInfo;
        console.log(JSON.stringify({{ events_len: events.length, on_event: events[0]?.[1]?.event || null }}));
        """
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["events_len"] == 1
    assert data["on_event"] == "on_case"
