from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.nodes import BrainOutput
from conversacion_simple.orchestration.pipeline import apply_brain_output_to_state
from conversacion_simple.state import build_default_conversation_simple_canonical_state
from negociacion.state.shared_types import ThreadMode


def _build_output() -> BrainOutput:
    return BrainOutput.model_validate(
        {
            "schema_version": "brain.v1",
            "status": "deliver",
            "assistant_response": {"text": "ok"},
            "state_patch": {
                "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "goal"},
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
