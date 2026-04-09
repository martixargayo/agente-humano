from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.contexts import ensure_conversacion_simple_session_context
from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from conversacion_simple.orchestration.pipeline import _call_brain_structured, run_conversacion_simple_turn
from conversacion_simple.services import build_conversacion_simple_turn_context
from sessions.state import SessionState


class _Response:
    def __init__(self, text: str):
        self.output_text = text
        self.id = "resp_test"


class _ResponsesApi:
    def __init__(self, text: str):
        self._text = text
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _Response(self._text)


class _Client:
    def __init__(self, text: str):
        self.responses = _ResponsesApi(text)


def test_brain_call_builds_explicit_provider_request_payload() -> None:
    payload = {
        "schema_version": "brain.v1",
        "status": "deliver",
        "assistant_response": {"text": "ok"},
        "state_patch": {
            "conversation_state": {"phase": None, "status": "active", "current_turn_goal": "g"},
            "memory_working": {"current_topic": None, "pending_question": None, "last_turn_summary": "x"},
            "memory_episodic_append": [],
        },
        "observability": {"rationale_summary": None},
    }
    client = _Client(json.dumps(payload, ensure_ascii=False))
    out = _call_brain_structured(client=client, model="gpt-5.4", messages=[{"role": "user", "content": "hola"}])

    assert out.source == "model"
    assert isinstance(out.provider_request, dict)
    request = out.provider_request or {}
    assert request.get("store") is False
    assert request.get("model") == "gpt-5.4"
    assert request.get("text", {}).get("format", {}).get("strict") is True


def test_turn_context_preserves_real_entry_surface() -> None:
    state = SessionState(user_id="u", session_id="s")
    ensure_conversacion_simple_session_context(state=state, requested_context_id="baseline")

    turn_context = build_conversacion_simple_turn_context(
        state=state,
        entrypoint="/api/interfaz_usuario/negociacion/turn",
        entry_surface="interfaz_usuario",
        context_source="interfaz_usuario_session_bound",
        requested_context_id="baseline",
    )

    assert turn_context.entry_surface == "interfaz_usuario"
    assert turn_context.context_source == "interfaz_usuario_session_bound"


def test_legacy_like_brain_payload_no_longer_coerced_and_uses_explicit_fallback() -> None:
    legacy_payload = {
        "reply": "texto legacy",
        "memory_patch": {"last_turn_summary": "legacy"},
    }
    client = _Client(json.dumps(legacy_payload, ensure_ascii=False))

    state = SessionState(user_id="u", session_id="s")
    ensure_conversacion_simple_session_context(state=state, requested_context_id="baseline")
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(
        state=state,
        entrypoint="/tests",
        entry_surface="tests",
        requested_context_id="baseline",
    )

    from conversacion_simple.orchestration import pipeline as cs_pipeline

    original_build_client = cs_pipeline._build_client
    cs_pipeline._build_client = lambda: client
    try:
        reply, updated, _meta = run_conversacion_simple_turn(
            state=state,
            user_message="hola",
            config=config,
            turn_context=turn_context,
        )
    finally:
        cs_pipeline._build_client = original_build_client

    assert "No pude completar la generación del turno" in reply
    traces = updated.world_state.get(config.traces_key, [])
    assert isinstance(traces, list) and traces
    latest = traces[-1]
    memory_obs = latest.get("memory_observability", {})
    assert memory_obs.get("brain_fallback_reason_code") == "validation_error_after_parse"
