from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.orchestration import pipeline


class _FakeResponse:
    def __init__(self, text: str | None, response_id: str = "resp_1") -> None:
        self.output_text = text
        self.id = response_id


class _FakeResponses:
    def __init__(self, outputs: list[str | None]) -> None:
        self._outputs = outputs
        self.calls = 0

    def create(self, **kwargs):
        idx = self.calls
        self.calls += 1
        text = self._outputs[idx] if idx < len(self._outputs) else self._outputs[-1]
        return _FakeResponse(text, response_id=f"resp_{idx+1}")


class _FakeClient:
    def __init__(self, outputs: list[str | None]) -> None:
        self.responses = _FakeResponses(outputs)


def _messages() -> list[dict[str, str]]:
    return [{"role": "developer", "content": "dev"}, {"role": "user", "content": "hola"}]


def test_brain_call_valid_json_no_retry() -> None:
    client = _FakeClient(['{"schema_version":"brain.v1","status":"clarify","assistant_response":{"text":"ok"},"state_patch":{"conversation_state":{"phase":null,"status":"active","current_turn_goal":"x","closure_readiness":"not_ready"},"memory_working":{"current_topic":null,"pending_question":null,"last_turn_summary":"x"},"memory_episodic_append":[]}}'])
    out = pipeline._call_brain_structured(client=client, model="x", messages=_messages())
    assert out.source == "model"
    assert out.fallback_reason_code is None
    assert out.retry_attempted is False


def test_brain_call_retry_succeeds_after_text_natural() -> None:
    client = _FakeClient([
        "respuesta natural no json",
        '{"schema_version":"brain.v1","status":"clarify","assistant_response":{"text":"ok"},"state_patch":{"conversation_state":{"phase":null,"status":"active","current_turn_goal":"x","closure_readiness":"not_ready"},"memory_working":{"current_topic":null,"pending_question":null,"last_turn_summary":"x"},"memory_episodic_append":[]}}',
    ])
    out = pipeline._call_brain_structured(client=client, model="x", messages=_messages())
    assert out.source == "model"
    assert out.retry_attempted is True
    assert out.retry_succeeded is True
    assert out.fallback_reason_code is None


def test_brain_call_retry_fails_and_fallback_json_parse_error() -> None:
    client = _FakeClient(["{\"bad\"", "```json\n{\"still_bad\"\n```"])
    out = pipeline._call_brain_structured(client=client, model="x", messages=_messages())
    assert out.source == "fallback"
    assert out.fallback_reason_code == "json_parse_error"
    assert out.retry_attempted is True
    assert out.retry_succeeded is False


def test_validation_error_after_parse_keeps_reason_without_retry() -> None:
    client = _FakeClient(['{"not":"brain_output"}'])
    call = pipeline._call_brain_structured(client=client, model="x", messages=_messages())
    brain_output, reason = pipeline._parse_brain_output_strict(payload=call.parsed_json, allow_fallback=True, user_message="hola", fallback_reason_code=call.fallback_reason_code)
    assert reason == "validation_error_after_parse"
    assert call.retry_attempted is False
    assert brain_output.assistant_response.text


def test_provider_exception_no_json_retry() -> None:
    class _BoomResponses:
        def __init__(self):
            self.calls = 0
        def create(self, **kwargs):
            self.calls += 1
            raise RuntimeError("provider down")
    class _BoomClient:
        def __init__(self):
            self.responses = _BoomResponses()
    client = _BoomClient()
    out = pipeline._call_brain_structured(client=client, model="x", messages=_messages())
    assert out.fallback_reason_code == "provider_exception"
    assert out.retry_attempted is False


def test_retry_logs_do_not_include_raw_output(caplog) -> None:
    caplog.set_level(logging.WARNING)
    long_text = "SENSITIVE_TRANSCRIPT_TEST_ABC"
    client = _FakeClient([long_text, "{bad"])
    pipeline._call_brain_structured(client=client, model="x", messages=_messages())
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "SENSITIVE_TRANSCRIPT_TEST_ABC" not in joined
    assert "output_len" in joined
