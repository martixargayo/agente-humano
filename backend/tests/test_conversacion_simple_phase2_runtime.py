from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from conversacion_simple.orchestration.pipeline import StructuredBrainCall, run_conversacion_simple_turn
from conversacion_simple.services import build_conversacion_simple_turn_context
from sessions.state import SessionState


def _bind(state: SessionState, context_id: str = "baseline") -> None:
    state.world_state["conversacion_simple_context"] = {
        "flow_id": "conversacion_simple",
        "context_id": context_id,
        "context_version": "1.0.0",
    }


def _valid_brain_output() -> dict:
    return {
        "schema_version": "brain.v1",
        "status": "deliver",
        "assistant_response": {"text": "respuesta brain"},
        "state_patch": {
            "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "avanzar"},
            "memory_working": {"current_topic": "tema", "pending_question": None, "last_turn_summary": "resumen"},
            "memory_episodic_append": [
                {"event_type": "important_fact", "event_summary": "hecho", "turn_id": "t1"}
            ],
        },
        "observability": {"rationale_summary": "ok"},
    }


def test_single_llm_call_per_turn(monkeypatch) -> None:
    calls = {"count": 0}

    def _fake_call(**kwargs):
        calls["count"] += 1
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output(), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, meta = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    assert calls["count"] == 1
    assert reply == "respuesta brain"
    assert meta["pipeline_topology"] == "single_llm"
    assert meta["node_names"] == ["brain"]
    assert meta["llm_call_count"] in {0, 1}
    assert updated.world_state[config.traces_key][-1]["pipeline_topology"] == "single_llm"


def test_invalid_brain_output_schema_raises(monkeypatch) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json={"schema_version": "brain.v1", "status": "deliver"}, response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    with pytest.raises(RuntimeError, match="conversacion_simple_brain_output_validation_error"):
        run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)


def test_legacy_response_text_payload_is_coerced(monkeypatch) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json={"response_text": "hola desde legacy"}, response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    assert reply == "hola desde legacy"
    assert updated.world_state[config.memory_key]["trace"]["last_status"] == "deliver"


def test_fallback_without_openai_key_returns_clarify() -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, meta = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    assert meta["llm_call_count"] == 0
    assert isinstance(meta.get("response_id"), (str, type(None)))
    assert updated.world_state[config.memory_key]["trace"]["last_status"] in {"clarify", "deliver", "refuse"}
    assert isinstance(reply, str) and reply


def test_recent_dialogue_updated() -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    recent = updated.world_state[config.recent_dialogue_key]
    assert len(recent) >= 2
    assert recent[-2]["role"] == "user"
    assert recent[-1]["role"] == "assistant"
    assert isinstance(reply, str) and reply


def test_context_precheck_mismatch_raises() -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state, context_id="baseline")
    config = build_conversacion_simple_pipeline_config(context_id="negociacion_sala_reuniones", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    with pytest.raises(RuntimeError):
        run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
