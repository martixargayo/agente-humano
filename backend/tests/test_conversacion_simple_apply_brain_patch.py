from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.nodes import BrainOutput
from conversacion_simple.orchestration.pipeline import apply_brain_output_to_state, _normalize_schema_for_strict_json_schema
from conversacion_simple.state import build_default_conversation_simple_canonical_state
from negociacion.state.shared_types import ThreadMode


def _build_output() -> BrainOutput:
    return BrainOutput.model_validate(
        {
            "schema_version": "brain.v1",
            "status": "deliver",
            "assistant_response": {"text": "ok"},
            "state_patch": {
                "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "goal", "closure_readiness": "not_ready"},
                "memory_working": {"current_topic": "tema", "pending_question": None, "last_turn_summary": "sum"},
                "memory_episodic_append": [
                    {"event_type": "important_fact", "event_summary": "fact", "turn_id": "t1"}
                ],
            },
            "observability": {"rationale_summary": "r"},
        }
    )


def test_apply_brain_output_to_state_is_deterministic() -> None:
    s1 = build_default_conversation_simple_canonical_state(session_id="s", thread_mode=ThreadMode.conversation, context_id="baseline")
    s2 = build_default_conversation_simple_canonical_state(session_id="s", thread_mode=ThreadMode.conversation, context_id="baseline")
    output = _build_output()

    apply_brain_output_to_state(canonical_state=s1, brain_output=output, turn_id="turn-x")
    apply_brain_output_to_state(canonical_state=s2, brain_output=output, turn_id="turn-x")

    assert s1.conversation_state.model_dump(mode="json") == s2.conversation_state.model_dump(mode="json")
    assert s1.memory_working.model_dump(mode="json") == s2.memory_working.model_dump(mode="json")
    assert [m.model_dump(mode="json") for m in s1.memory_episodic] == [m.model_dump(mode="json") for m in s2.memory_episodic]
    assert s1.trace.turn_id == "turn-x"
    assert len(s1.memory_episodic) == 1
    assert s1.ui_state.finish_button_armed is False


def test_apply_brain_output_sets_finish_button_when_closure_ready_and_latches() -> None:
    state = build_default_conversation_simple_canonical_state(session_id="s", thread_mode=ThreadMode.conversation, context_id="baseline")
    ready_output = BrainOutput.model_validate(
        {
            "schema_version": "brain.v1",
            "status": "deliver",
            "assistant_response": {"text": "cerramos"},
            "state_patch": {
                "conversation_state": {"phase": "cierre", "status": "active", "current_turn_goal": "confirmar", "closure_readiness": "ready"},
                "memory_working": {"current_topic": "tema", "pending_question": None, "last_turn_summary": "ok"},
                "memory_episodic_append": [],
            },
        }
    )
    not_ready_output = BrainOutput.model_validate(
        {
            "schema_version": "brain.v1",
            "status": "deliver",
            "assistant_response": {"text": "matiz"},
            "state_patch": {
                "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "afinar", "closure_readiness": "not_ready"},
                "memory_working": {"current_topic": "tema", "pending_question": None, "last_turn_summary": "ok"},
                "memory_episodic_append": [],
            },
        }
    )

    apply_brain_output_to_state(canonical_state=state, brain_output=ready_output, turn_id="turn-ready")
    assert state.ui_state.finish_button_armed is True
    assert state.conversation_state.closure_readiness == "ready"

    apply_brain_output_to_state(canonical_state=state, brain_output=not_ready_output, turn_id="turn-after")
    assert state.ui_state.finish_button_armed is True
    assert state.conversation_state.closure_readiness == "not_ready"


def test_schema_normalization_preserves_pydantic_required_keys() -> None:
    base = BrainOutput.model_json_schema()
    normalized = _normalize_schema_for_strict_json_schema(base)
    assert "observability" in normalized.get("required", [])
    assert "rationale_summary" in normalized.get("$defs", {}).get("BrainObservability", {}).get("required", [])
    assert "memory_episodic_append" in normalized.get("$defs", {}).get("BrainStatePatch", {}).get("required", [])
