from __future__ import annotations

from pathlib import Path


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
