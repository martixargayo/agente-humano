from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from conversacion_simple.orchestration.pipeline import StructuredBrainCall, run_conversacion_simple_turn
from conversacion_simple.services import build_conversacion_simple_turn_context
from sessions.state import SessionState


def _bind(state: SessionState, context_id: str) -> None:
    state.world_state["conversacion_simple_context"] = {
        "flow_id": "conversacion_simple",
        "context_id": context_id,
        "context_version": "1.0.0",
    }


def _brain_output() -> dict:
    return {
        "schema_version": "brain.v1",
        "status": "deliver",
        "assistant_response": {"text": "ok"},
        "state_patch": {
            "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "avanzar"},
            "memory_working": {"current_topic": "tema", "pending_question": None, "last_turn_summary": "resumen"},
            "memory_episodic_append": [{"event_type": "important_fact", "event_summary": "fact", "turn_id": "t1"}],
        },
        "observability": {"rationale_summary": "ok"},
    }


def test_trace_envelope_has_external_contract_and_deliberate_node_divergence(monkeypatch) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=_brain_output(), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state, "baseline")
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    _reply, updated, meta = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
    trace = updated.world_state[config.traces_key][-1]

    assert trace["pipeline_topology"] == "single_llm"
    assert set(trace["nodes"].keys()) == {"brain"}
    assert "memory_observability" in trace
    assert meta["node_names"] == ["brain"]
    assert meta["pipeline_topology"] == "single_llm"


def test_state_shape_persistence_keys_are_stable() -> None:
    state = SessionState(user_id="u", session_id="s")
    state.world_state["conversation_simple_canonical"] = {}
    state.world_state["conversation_simple_canonical_recent_dialogue"] = []
    state.world_state["conversation_simple_canonical_traces"] = []

    assert "conversation_simple_canonical" in state.world_state
    assert "conversation_simple_canonical_recent_dialogue" in state.world_state
    assert "conversation_simple_canonical_traces" in state.world_state
