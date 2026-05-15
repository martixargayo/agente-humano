from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


APP_JS = Path("backend/interfaz_usuario_app/app.js")


def _extract_transcribe_block(src: str) -> str:
    start = src.index("async function transcribeAudio(blob, metadata = {})")
    end = src.index("async function playTtsWithAvatar(replyText)", start)
    return src[start:end]


def _extract_handle_finish_block(src: str) -> str:
    start = src.index("async function handleFinishTurn()")
    end = src.index("ui.finishTurnBtn.addEventListener('click'", start)
    return src[start:end]


def _run_node(script: str) -> str:
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"Node test failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result.stdout


def test_transcribe_audio_error_and_success_matrix() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    fn_block = _extract_transcribe_block(src)
    script = textwrap.dedent(
        f"""
        const src = {json.dumps(fn_block)};
        globalThis.recorderMimeType = 'audio/webm';
        globalThis.recordingStartedAtMs = Date.now();
        globalThis.recordTurnPerf = () => {{}};
        globalThis.voiceDebug = () => {{}};
        eval(src);

        const originalFetch = globalThis.fetch;

        async function run() {{
          const blob = new Blob(['abc'], {{ type: 'audio/webm' }});

          globalThis.fetch = async () => ({{ ok:false, text: async () => '{{"detail":"No hay proveedor STT disponible (Google/OpenAI)."}}' }});
          let err503 = '';
          try {{ await transcribeAudio(blob); }} catch (e) {{ err503 = String(e.message || e); }}

          globalThis.fetch = async () => ({{ ok:false, text: async () => '{{"detail":"Archivo de audio vacío. Repítelo de nuevo asegurándote de que el micrófono está activo."}}' }});
          let err400 = '';
          try {{ await transcribeAudio(blob); }} catch (e) {{ err400 = String(e.message || e); }}

          globalThis.fetch = async () => ({{ ok:false, text: async () => '{{"detail":"Audio demasiado largo. Repítelo de forma más breve."}}' }});
          let errTooLong = '';
          try {{ await transcribeAudio(blob); }} catch (e) {{ errTooLong = String(e.message || e); }}

          globalThis.fetch = async () => {{ throw new TypeError('Failed to fetch'); }};
          let errNetwork = '';
          try {{ await transcribeAudio(blob); }} catch (e) {{ errNetwork = String(e.message || e); }}

          globalThis.fetch = async () => ({{ ok:true, json: async () => {{ throw new SyntaxError('Unexpected token'); }} }});
          let errJson = '';
          try {{ await transcribeAudio(blob); }} catch (e) {{ errJson = String(e.message || e); }}

          globalThis.fetch = async () => ({{ ok:true, json: async () => ({{ text: '   ' }}) }});
          const emptyText = await transcribeAudio(blob);

          globalThis.fetch = async () => ({{ ok:true, json: async () => ({{ text: ' hola mundo ' }}) }});
          const okText = await transcribeAudio(blob);

          console.log(JSON.stringify({{ err503, err400, errTooLong, errNetwork, errJson, emptyText, okText }}));
        }}

        run().finally(() => {{ globalThis.fetch = originalFetch; }});
        """
    )
    out = _run_node(script).strip().splitlines()[-1]
    data = json.loads(out)
    assert "No hay proveedor STT disponible" in data["err503"]
    assert data["err400"] == "Archivo de audio vacío. Repítelo de nuevo asegurándote de que el micrófono está activo."
    assert data["errTooLong"] == "Audio demasiado largo. Repítelo de forma más breve."
    assert "Failed to fetch" in data["errNetwork"]
    assert "Unexpected token" in data["errJson"]
    assert data["emptyText"] == ""
    assert data["okText"] == "hola mundo"


def test_transcribe_audio_sends_recording_duration_and_metadata() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    fn_block = _extract_transcribe_block(src)
    script = textwrap.dedent(
        f"""
        const src = {json.dumps(fn_block)};
        globalThis.recorderMimeType = 'audio/webm';
        globalThis.recordingStartedAtMs = Date.now();
        globalThis.recordTurnPerf = () => {{}};
        globalThis.voiceDebug = () => {{}};
        eval(src);
        async function run() {{
          const blob = new Blob(['abc'], {{ type: 'audio/webm' }});
          let captured = {{}};
          globalThis.fetch = async (_url, options) => {{
            const fd = options.body;
            captured.recording_duration_ms = fd.get('recording_duration_ms');
            captured.voice_turn_id = fd.get('voice_turn_id');
            captured.source = fd.get('source');
            captured.correlation_id = fd.get('correlation_id');
            return {{ ok: true, status: 200, json: async () => ({{ text: 'ok' }}) }};
          }};
          await transcribeAudio(blob, {{ recording_duration_ms: 1234, voice_turn_id: 'voice-1', source: 'button', correlation_id: 'abc' }});
          console.log(JSON.stringify(captured));
        }}
        run();
        """
    )
    out = _run_node(script).strip().splitlines()[-1]
    data = json.loads(out)
    assert data["recording_duration_ms"] == "1234"
    assert data["voice_turn_id"] == "voice-1"
    assert data["source"] == "button"
    assert data["correlation_id"] == "abc"


def test_handle_finish_turn_releases_inflight_and_retries_after_error() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    fn_block = _extract_handle_finish_block(src)
    script = textwrap.dedent(
        f"""
        const src = {json.dumps(fn_block)};
        globalThis.InputMode = {{ TALK: 'talk', WRITE: 'write' }};
        globalThis.currentInputMode = InputMode.TALK;
        globalThis.turnInFlight = false;
        globalThis.voiceTurnInFlight = false;
        globalThis.ui = {{
          finishTurnBtn: {{ disabled: false, classList: {{ remove(){{}}, add(){{}} }}, offsetWidth: 0 }},
          statusText: {{ textContent: '' }},
        }};
        globalThis.recordTurnPerf = () => {{}};
        globalThis.updateUi = () => {{ globalThis.uiUpdates = (globalThis.uiUpdates || 0) + 1; }};
        globalThis.setStatusText = (t) => {{ ui.statusText.textContent = t; }};
        globalThis.setStatusWarning = (t) => {{ ui.statusText.textContent = `⚠️ ${{t}}`; }};
        globalThis.isVoiceStatusWarningMessage = (m) => [
          'Transcripción vacía. Repítelo de nuevo asegurándote de que el micrófono está activo.',
          'No se capturó audio. Repítelo de nuevo asegurándote de que el micrófono está activo.',
          'Archivo de audio vacío. Repítelo de nuevo asegurándote de que el micrófono está activo.',
          'Audio demasiado largo. Repítelo de forma más breve.',
        ].includes(m);
        globalThis.getActiveSessionBusyState = () => null;
        globalThis.isSessionBusyError = () => false;
        globalThis.teardownMic = () => {{}};
        globalThis.syncAvatarMode = () => {{}};
        globalThis.startVoiceCapture = async () => {{ globalThis.restarts = (globalThis.restarts || 0) + 1; }};
        globalThis.stopVoiceCapture = async () => new Blob(['audio'], {{ type: 'audio/webm' }});
        globalThis.runNegotiationTurnFromText = async () => true;
        globalThis.audioChunks = [];
        globalThis.recorderMimeType = 'audio/webm';
        globalThis.recordingStartedAtMs = Date.now();
        globalThis.latestVoiceActionMeta = {{ source: 'unknown', correlation_id: null }};
        globalThis.currentVoiceDebugContext = null;
        globalThis.voiceDebug = () => {{}};

        eval(src);

        async function run() {{
          let transcribeCalls = 0;

          transcribeAudio = async () => {{ transcribeCalls += 1; throw new Error('503 stt'); }};
          await handleFinishTurn();
          const after503 = {{ inflight: voiceTurnInFlight, restarts, transcribeCalls }};

          transcribeAudio = async () => {{ transcribeCalls += 1; return ''; }};
          await handleFinishTurn();
          const afterEmptyText = {{ inflight: voiceTurnInFlight, restarts, transcribeCalls, status: ui.statusText.textContent }};

          transcribeAudio = async () => {{ transcribeCalls += 1; throw new Error('Audio demasiado largo. Repítelo de forma más breve.'); }};
          await handleFinishTurn();
          const afterTooLong = {{ inflight: voiceTurnInFlight, restarts, transcribeCalls, status: ui.statusText.textContent }};

          transcribeAudio = async () => {{ transcribeCalls += 1; return 'ok'; }};
          runNegotiationTurnFromText = async () => {{ throw new Error('pipeline fail'); }};
          await handleFinishTurn();
          const afterPipelineError = {{ inflight: voiceTurnInFlight, restarts, transcribeCalls }};

          stopVoiceCapture = async () => new Blob([], {{ type: 'audio/webm' }});
          const beforeBlobZero = transcribeCalls;
          await handleFinishTurn();
          const afterBlobZero = {{ inflight: voiceTurnInFlight, transcribeCallsDelta: transcribeCalls - beforeBlobZero, status: ui.statusText.textContent }};

          console.log(JSON.stringify({{ after503, afterEmptyText, afterTooLong, afterPipelineError, afterBlobZero }}));
        }}

        run().catch((err) => {{ console.error(err); process.exit(1); }});
        """
    )
    out = _run_node(script).strip().splitlines()[-1]
    data = json.loads(out)
    assert data["after503"]["inflight"] is False
    assert data["afterEmptyText"]["inflight"] is False
    assert data["afterEmptyText"]["status"] == "⚠️ Transcripción vacía. Repítelo de nuevo asegurándote de que el micrófono está activo."
    assert data["afterTooLong"]["inflight"] is False
    assert data["afterTooLong"]["status"] == "⚠️ Audio demasiado largo. Repítelo de forma más breve."
    assert data["afterPipelineError"]["inflight"] is False
    assert data["afterBlobZero"]["transcribeCallsDelta"] == 0
    assert data["afterBlobZero"]["status"] == "⚠️ No se capturó audio. Repítelo de nuevo asegurándote de que el micrófono está activo."


def test_generic_fallback_phrase_originates_in_pipeline_not_voice_frontend() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    assert "No pude completar la generación del turno en este intento" not in src

    pipeline_src = Path("backend/conversacion_simple/orchestration/pipeline.py").read_text(encoding="utf-8")
    assert "No pude completar la generación del turno en este intento. ¿Puedes repetir tu último mensaje?" in pipeline_src
    assert "def _brain_fallback" in pipeline_src


def test_handle_finish_turn_double_call_results_in_single_stt_attempt() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    fn_block = _extract_handle_finish_block(src)
    script = textwrap.dedent(
        f"""
        const src = {json.dumps(fn_block)};
        globalThis.InputMode = {{ TALK: 'talk', WRITE: 'write' }};
        globalThis.currentInputMode = InputMode.TALK;
        globalThis.turnInFlight = false;
        globalThis.voiceTurnInFlight = false;
        globalThis.ui = {{
          finishTurnBtn: {{ disabled: false, classList: {{ remove(){{}}, add(){{}} }}, offsetWidth: 0 }},
          statusText: {{ textContent: '' }},
        }};
        globalThis.recordTurnPerf = () => {{}};
        globalThis.updateUi = () => {{}};
        globalThis.setStatusText = () => {{}};
        globalThis.getActiveSessionBusyState = () => null;
        globalThis.isSessionBusyError = () => false;
        globalThis.teardownMic = () => {{}};
        globalThis.syncAvatarMode = () => {{}};
        globalThis.startVoiceCapture = async () => {{}};

        let stopResolve;
        globalThis.stopVoiceCapture = async () => await new Promise((resolve) => {{ stopResolve = resolve; }});
        globalThis.runNegotiationTurnFromText = async () => true;
        globalThis.audioChunks = [];
        globalThis.recorderMimeType = 'audio/webm';
        globalThis.recordingStartedAtMs = Date.now();
        globalThis.latestVoiceActionMeta = {{ source: 'unknown', correlation_id: null }};
        globalThis.currentVoiceDebugContext = null;
        globalThis.voiceDebug = () => {{}};

        eval(src);

        async function run() {{
          let transcribeCalls = 0;
          transcribeAudio = async () => {{ transcribeCalls += 1; return 'ok'; }};

          const p1 = handleFinishTurn();
          const p2 = handleFinishTurn();

          stopResolve(new Blob(['audio'], {{ type: 'audio/webm' }}));
          await Promise.all([p1, p2]);

          console.log(JSON.stringify({{ transcribeCalls }}));
        }}

        run().catch((err) => {{ console.error(err); process.exit(1); }});
        """
    )
    out = _run_node(script).strip().splitlines()[-1]
    data = json.loads(out)
    assert data["transcribeCalls"] == 1


def test_voice_turn_reconstruction_sequence_with_single_voice_turn_id() -> None:
    src = APP_JS.read_text(encoding="utf-8")
    fn_block = _extract_handle_finish_block(src)
    script = textwrap.dedent(
        f"""
        const src = {json.dumps(fn_block)};
        globalThis.InputMode = {{ TALK: 'talk', WRITE: 'write' }};
        globalThis.currentInputMode = InputMode.TALK;
        globalThis.turnInFlight = false;
        globalThis.voiceTurnInFlight = false;
        globalThis.ui = {{
          finishTurnBtn: {{ disabled: false, classList: {{ remove(){{}}, add(){{}} }}, offsetWidth: 0 }},
          statusText: {{ textContent: '' }},
        }};
        globalThis.recordTurnPerf = () => {{}};
        globalThis.updateUi = () => {{}};
        globalThis.setStatusText = () => {{}};
        globalThis.getActiveSessionBusyState = () => null;
        globalThis.isSessionBusyError = () => false;
        globalThis.teardownMic = () => {{}};
        globalThis.syncAvatarMode = () => {{}};
        globalThis.startVoiceCapture = async () => {{}};
        globalThis.stopVoiceCapture = async () => new Blob(['audio'], {{ type: 'audio/webm' }});
        globalThis.runNegotiationTurnFromText = async () => true;
        globalThis.transcribeAudio = async () => 'texto transcrito';
        globalThis.latestVoiceActionMeta = {{ source: 'button', correlation_id: null }};
        globalThis.currentVoiceDebugContext = null;
        globalThis.audioChunks = [];
        globalThis.recorderMimeType = 'audio/webm';
        globalThis.recordingStartedAtMs = Date.now();
        const events = [];
        globalThis.voiceDebug = (event, payload) => {{
          events.push({{ event, voice_turn_id: currentVoiceDebugContext?.voice_turn_id || null, payload }});
        }};
        eval(src);
        handleFinishTurn().then(() => {{
          const seq = events.map((e) => e.event);
          const ids = [...new Set(events.map((e) => e.voice_turn_id).filter(Boolean))];
          console.log(JSON.stringify({{ seq, ids_len: ids.length }}));
        }});
        """
    )
    out = _run_node(script).strip().splitlines()[-1]
    data = json.loads(out)
    assert "voice_turn_start" in data["seq"]
    assert "voice_capture_stop_result" in data["seq"]
    assert "pipeline_call" in data["seq"]
    assert "pipeline_result" in data["seq"]
    assert "voice_turn_end" in data["seq"]
    assert data["ids_len"] == 1
