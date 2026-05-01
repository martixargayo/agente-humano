from __future__ import annotations

import io
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import logging

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import app as api_app_module


client = TestClient(api_app_module.app)


def _post_audio(payload: bytes = b"audio", data: dict[str, str] | None = None):
    return client.post(
        "/stt_google",
        data=data or {},
        files={"file": ("audio.webm", io.BytesIO(payload), "audio/webm")},
    )


def test_stt_google_returns_400_for_empty_audio_file() -> None:
    response = _post_audio(payload=b"")
    assert response.status_code == 400
    assert response.json()["detail"] == "Archivo de audio vacío."


def test_stt_google_returns_503_when_no_google_and_no_openai(monkeypatch) -> None:
    monkeypatch.setattr(api_app_module, "speech_client", None)
    monkeypatch.setattr(api_app_module, "openai_client", None)

    response = _post_audio()
    assert response.status_code == 503
    assert response.json()["detail"] == "No hay proveedor STT disponible (Google/OpenAI)."


def test_stt_google_returns_503_when_google_runtime_fails_and_no_openai(monkeypatch) -> None:
    class FailingGoogleClient:
        def recognize(self, **kwargs):
            raise RuntimeError("google down")

    monkeypatch.setattr(api_app_module, "speech_client", FailingGoogleClient())
    monkeypatch.setattr(api_app_module, "openai_client", None)

    response = _post_audio()
    assert response.status_code == 503
    # Mensaje idéntico al caso sin configuración: no distingue ausencia de proveedor vs fallo runtime.
    assert response.json()["detail"] == "No hay proveedor STT disponible (Google/OpenAI)."


def test_stt_google_returns_200_when_google_fails_and_openai_succeeds(monkeypatch) -> None:
    class FailingGoogleClient:
        def recognize(self, **kwargs):
            raise RuntimeError("google down")

    class Transcription:
        text = "texto desde openai"

    class FakeOpenAIAudioTranscriptions:
        @staticmethod
        def create(**kwargs):
            return Transcription()

    class FakeOpenAIAudio:
        transcriptions = FakeOpenAIAudioTranscriptions()

    class FakeOpenAIClient:
        audio = FakeOpenAIAudio()

    monkeypatch.setattr(api_app_module, "speech_client", FailingGoogleClient())
    monkeypatch.setattr(api_app_module, "openai_client", FakeOpenAIClient())

    response = _post_audio()
    assert response.status_code == 200
    assert response.json()["text"] == "texto desde openai"


def test_stt_google_returns_503_when_only_openai_configured_but_runtime_fails(monkeypatch) -> None:
    class FailingTranscriptions:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("openai down")

    class FakeOpenAIAudio:
        transcriptions = FailingTranscriptions()

    class FakeOpenAIClient:
        audio = FakeOpenAIAudio()

    monkeypatch.setattr(api_app_module, "speech_client", None)
    monkeypatch.setattr(api_app_module, "openai_client", FakeOpenAIClient())

    response = _post_audio()
    assert response.status_code == 503
    # Mensaje idéntico al caso sin proveedores: ambigüedad intencional del comportamiento actual.
    assert response.json()["detail"] == "No hay proveedor STT disponible (Google/OpenAI)."


def test_build_speech_client_uses_google_application_credentials_file_first(monkeypatch, tmp_path) -> None:
    creds_file = tmp_path / "gcp.json"
    creds_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds_file))
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"client_email":"json@example.com","project_id":"json-proj"}')

    class FakeCreds:
        service_account_email = "file@example.com"
        project_id = "file-proj"

    monkeypatch.setattr(api_app_module.service_account.Credentials, "from_service_account_file", lambda path: FakeCreds())
    monkeypatch.setattr(api_app_module.service_account.Credentials, "from_service_account_info", lambda info: (_ for _ in ()).throw(RuntimeError("should not be called")))
    monkeypatch.setattr(api_app_module.speech, "SpeechClient", lambda credentials=None: {"credentials": credentials})

    client = api_app_module._build_speech_client()
    assert client is not None
    assert client["credentials"].service_account_email == "file@example.com"


def test_build_speech_client_supports_google_service_account_json(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "/tmp/does-not-exist.json")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"client_email":"svc@example.com","project_id":"proj-1"}')

    class FakeCreds:
        service_account_email = "svc@example.com"
        project_id = "proj-1"

    monkeypatch.setattr(api_app_module.service_account.Credentials, "from_service_account_info", lambda info: FakeCreds())
    monkeypatch.setattr(api_app_module.speech, "SpeechClient", lambda credentials=None: {"credentials": credentials})

    client = api_app_module._build_speech_client()
    assert client is not None
    assert client["credentials"].service_account_email == "svc@example.com"


def test_build_speech_client_invalid_json_does_not_crash_and_does_not_log_private_key(monkeypatch, caplog) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "/tmp/does-not-exist.json")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"private_key":"SUPER_SECRET","broken":')
    monkeypatch.setattr(api_app_module.speech, "SpeechClient", lambda credentials=None: {"credentials": credentials})

    client = api_app_module._build_speech_client()
    assert client is None
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "private_key" not in joined
    assert "SUPER_SECRET" not in joined


def test_voice_debug_backend_off_emits_no_debug_logs(monkeypatch, caplog) -> None:
    monkeypatch.setattr(api_app_module, "VOICE_DEBUG_BACKEND", False)
    caplog.set_level(logging.INFO)
    api_app_module._voice_debug_log("test_event", sample=1)
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "voice_debug_backend" not in joined


def test_voice_debug_backend_on_stt_empty_audio_logs_status_400(monkeypatch, caplog) -> None:
    monkeypatch.setattr(api_app_module, "VOICE_DEBUG_BACKEND", True)
    monkeypatch.setattr(api_app_module, "speech_client", None)
    monkeypatch.setattr(api_app_module, "openai_client", None)
    caplog.set_level(logging.INFO)
    response = _post_audio(payload=b"")
    assert response.status_code == 400
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "stt_backend_request" in joined
    assert "status': 400" in joined or "status=400" in joined


def test_stt_config_webm_opus_without_env_uses_48000(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_STT_SAMPLE_RATE_HERTZ", raising=False)
    monkeypatch.delenv("GOOGLE_STT_SAMPLE_RATE", raising=False)
    monkeypatch.delenv("SAMPLE_RATE", raising=False)
    sample, source = api_app_module._resolve_stt_sample_rate_hertz("WEBM_OPUS")
    assert sample == 48000
    assert source == "default_opus_48000"


def test_stt_config_webm_opus_with_env_uses_env_value(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_STT_SAMPLE_RATE_HERTZ", "16000")
    sample, source = api_app_module._resolve_stt_sample_rate_hertz("WEBM_OPUS")
    assert sample == 16000
    assert source == "env"


def test_stt_config_webm_opus_zero_falls_back_to_48000(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_STT_SAMPLE_RATE_HERTZ", "0")
    sample, source = api_app_module._resolve_stt_sample_rate_hertz("WEBM_OPUS")
    assert sample == 48000
    assert source == "default_opus_48000"


def test_stt_config_webm_opus_invalid_falls_back_to_48000(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_STT_SAMPLE_RATE_HERTZ", "abc")
    sample, source = api_app_module._resolve_stt_sample_rate_hertz("WEBM_OPUS")
    assert sample == 48000
    assert source == "default_opus_48000"


def test_stt_config_non_opus_omits_sample_rate_when_absent(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_STT_SAMPLE_RATE_HERTZ", raising=False)
    monkeypatch.delenv("GOOGLE_STT_SAMPLE_RATE", raising=False)
    monkeypatch.delenv("SAMPLE_RATE", raising=False)
    sample, source = api_app_module._resolve_stt_sample_rate_hertz("LINEAR16")
    assert sample is None
    assert source == "omitted"


def test_stt_google_google_call_never_receives_sample_rate_zero(monkeypatch) -> None:
    class FakeGoogleResponse:
        results = []

    captured = {}

    class FakeGoogleClient:
        def recognize(self, **kwargs):
            captured["config"] = kwargs.get("config")
            return FakeGoogleResponse()

    monkeypatch.setattr(api_app_module, "speech_client", FakeGoogleClient())
    monkeypatch.setattr(api_app_module, "openai_client", None)
    monkeypatch.setattr(api_app_module, "stt_config", api_app_module.speech.RecognitionConfig(
        language_code="es-ES",
        enable_automatic_punctuation=True,
        model="latest_short",
        encoding=getattr(api_app_module.speech.RecognitionConfig.AudioEncoding, "WEBM_OPUS"),
        sample_rate_hertz=48000,
    ))

    response = _post_audio(payload=b"audio")
    assert response.status_code == 200
    assert captured["config"].sample_rate_hertz != 0


def test_stt_google_duration_absent_keeps_google_first(monkeypatch) -> None:
    calls: list[str] = []

    class FakeGoogle:
        def recognize(self, **kwargs):
            calls.append("google")
            class R:
                results = []
            return R()

    monkeypatch.setattr(api_app_module, "speech_client", FakeGoogle())
    monkeypatch.setattr(api_app_module, "openai_client", None)
    response = _post_audio(payload=b"audio")
    assert response.status_code == 200
    assert calls == ["google"]


def test_stt_google_duration_short_keeps_google_first(monkeypatch) -> None:
    calls: list[str] = []

    class FakeGoogle:
        def recognize(self, **kwargs):
            calls.append("google")
            class R:
                results = []
            return R()

    monkeypatch.setattr(api_app_module, "speech_client", FakeGoogle())
    monkeypatch.setattr(api_app_module, "openai_client", None)
    response = _post_audio(payload=b"audio", data={"recording_duration_ms": "5000"})
    assert response.status_code == 200
    assert calls == ["google"]


def test_stt_google_duration_long_routes_openai_direct(monkeypatch) -> None:
    calls: list[str] = []

    class FakeGoogle:
        def recognize(self, **kwargs):
            calls.append("google")
            raise RuntimeError("should not be called")

    class T:
        text = "ok from openai"

    class AudioTrans:
        @staticmethod
        def create(**kwargs):
            calls.append("openai")
            return T()

    class Audio:
        transcriptions = AudioTrans()

    class OpenAIClient:
        audio = Audio()

    monkeypatch.setattr(api_app_module, "speech_client", FakeGoogle())
    monkeypatch.setattr(api_app_module, "openai_client", OpenAIClient())
    response = _post_audio(payload=b"audio", data={"recording_duration_ms": "70000"})
    assert response.status_code == 200
    assert calls == ["openai"]


def test_stt_google_duration_too_long_rejected(monkeypatch) -> None:
    monkeypatch.setattr(api_app_module, "speech_client", None)
    monkeypatch.setattr(api_app_module, "openai_client", None)
    response = _post_audio(payload=b"audio", data={"recording_duration_ms": "130000"})
    assert response.status_code == 400
    assert "Audio demasiado largo" in response.json()["detail"]


def test_stt_google_duration_invalid_is_compatible(monkeypatch) -> None:
    calls: list[str] = []

    class FakeGoogle:
        def recognize(self, **kwargs):
            calls.append("google")
            class R:
                results = []
            return R()

    monkeypatch.setattr(api_app_module, "speech_client", FakeGoogle())
    monkeypatch.setattr(api_app_module, "openai_client", None)
    response = _post_audio(payload=b"audio", data={"recording_duration_ms": "bad"})
    assert response.status_code == 200
    assert calls == ["google"]
