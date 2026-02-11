import base64

from fastapi.testclient import TestClient

import app


class _FakeAudioResponse:
    def __init__(self, payload: bytes):
        self.content = payload

    def read(self) -> bytes:
        return self.content


class _FakeSpeechAPI:
    @staticmethod
    def create(**kwargs):
        _ = kwargs
        return _FakeAudioResponse(b"FAKE_WAV_BYTES")


class _FakeOpenAIClient:
    class audio:  # noqa: N801 - emulate SDK shape
        speech = _FakeSpeechAPI()


class _FakeAlternative:
    transcript = "hola vendedor"


class _FakeResult:
    alternatives = [_FakeAlternative()]


class _FakeSpeechResponse:
    results = [_FakeResult()]


class _FakeGoogleSpeechClient:
    @staticmethod
    def recognize(config, audio):
        _ = (config, audio)
        return _FakeSpeechResponse()


def test_interface_like_flow_chat_negotiation_stt_tts(monkeypatch):
    # Simula dependencias externas que en producción usa la interfaz.
    monkeypatch.setattr(app, "openai_client", _FakeOpenAIClient())
    monkeypatch.setattr(app, "speech_client", _FakeGoogleSpeechClient())
    monkeypatch.setattr(app, "get_session_state", lambda user_id, session_id: {"u": user_id, "s": session_id})
    monkeypatch.setattr(app, "run_agent", lambda state, message: (f"chat:{message}", state))
    monkeypatch.setattr(app, "run_negotiation_agent", lambda state, message: (f"negociar:{message}", state))

    with TestClient(app.app) as client:
        demo = client.get("/demo")
        assert demo.status_code == 200
        assert "/chat" in demo.text
        assert "/negociar" in demo.text

        tts = client.post("/tts", json={"text": "Hola, ¿en qué puedo ayudarte?"})
        assert tts.status_code == 200
        tts_payload = tts.json()
        assert tts_payload["audio_mime_type"] == "audio/wav"
        assert base64.b64decode(tts_payload["audio_base64"]) == b"FAKE_WAV_BYTES"

        stt = client.post(
            "/stt_google",
            files={"file": ("audio.webm", b"dummy audio bytes", "audio/webm")},
        )
        assert stt.status_code == 200
        assert stt.json()["text"] == "hola vendedor"

        chat = client.post(
            "/chat",
            json={"user_id": "u1", "session_id": "s1", "message": "hola"},
        )
        assert chat.status_code == 200
        assert chat.json()["reply"] == "chat:hola"

        negociar = client.post(
            "/negociar",
            json={"user_id": "u1", "session_id": "s1", "message": "vamos a negociar"},
        )
        assert negociar.status_code == 200
        assert negociar.json()["reply"] == "negociar:vamos a negociar"


def test_negociar_endpoint_no_500_when_agent_ok(monkeypatch):
    monkeypatch.setattr(app, "get_session_state", lambda user_id, session_id: {"u": user_id, "s": session_id})
    monkeypatch.setattr(app, "run_negotiation_agent", lambda state, message: ("ok", state))

    with TestClient(app.app) as client:
        resp = client.post(
            "/negociar",
            json={"user_id": "usuario_real", "session_id": "sesion_real", "message": "¿cerramos en 9500?"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"reply": "ok"}
