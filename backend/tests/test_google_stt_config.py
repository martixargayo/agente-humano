from __future__ import annotations

import json

from api import app as app_module


def test_build_speech_client_prefers_service_account_json(monkeypatch):
    calls: list[tuple[str, object]] = []

    monkeypatch.setenv(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        json.dumps({"type": "service_account", "project_id": "demo"}),
    )
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "/tmp/unused.json")
    monkeypatch.setattr(app_module.os.path, "exists", lambda _path: True)

    monkeypatch.setattr(
        app_module.service_account.Credentials,
        "from_service_account_info",
        lambda info: calls.append(("info", info)) or "creds-from-info",
    )
    monkeypatch.setattr(
        app_module.service_account.Credentials,
        "from_service_account_file",
        lambda path: calls.append(("file", path)) or "creds-from-file",
    )

    class DummySpeechClient:
        def __init__(self, credentials=None):
            calls.append(("client", credentials))
            self.credentials = credentials

    monkeypatch.setattr(app_module.speech, "SpeechClient", DummySpeechClient)

    client = app_module._build_speech_client()

    assert isinstance(client, DummySpeechClient)
    assert calls == [
        ("info", {"type": "service_account", "project_id": "demo"}),
        ("client", "creds-from-info"),
    ]



def test_build_speech_client_uses_path_when_env_json_missing(monkeypatch):
    calls: list[tuple[str, object]] = []

    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "/tmp/google.json")
    monkeypatch.setattr(app_module.os.path, "exists", lambda path: path == "/tmp/google.json")

    monkeypatch.setattr(
        app_module.service_account.Credentials,
        "from_service_account_file",
        lambda path: calls.append(("file", path)) or "creds-from-file",
    )

    class DummySpeechClient:
        def __init__(self, credentials=None):
            calls.append(("client", credentials))
            self.credentials = credentials

    monkeypatch.setattr(app_module.speech, "SpeechClient", DummySpeechClient)

    client = app_module._build_speech_client()

    assert isinstance(client, DummySpeechClient)
    assert calls == [
        ("file", "/tmp/google.json"),
        ("client", "creds-from-file"),
    ]



def test_build_speech_client_returns_none_when_google_credentials_fail(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{invalid-json")
    monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
    monkeypatch.setattr(app_module.os.path, "exists", lambda _path: False)

    client = app_module._build_speech_client()

    assert client is None
