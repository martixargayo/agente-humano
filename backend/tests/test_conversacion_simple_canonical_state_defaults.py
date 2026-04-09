from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.orchestration.flow_config import (
    CONVERSATION_SIMPLE_MEMORY_KEY,
    CONVERSATION_SIMPLE_RECENT_DIALOGUE_KEY,
    CONVERSATION_SIMPLE_TRACES_KEY,
    build_conversacion_simple_pipeline_config,
)
from conversacion_simple.nodes import BrainOutput
from conversacion_simple.services import build_conversacion_simple_turn_context
from conversacion_simple.state import ConversationSimpleCanonicalState, build_default_conversation_simple_canonical_state
from negociacion.state.shared_types import ThreadMode
from sessions.state import SessionState


def test_default_canonical_state_and_config_keys() -> None:
    state = build_default_conversation_simple_canonical_state(
        session_id="s",
        user_id="u",
        thread_mode=ThreadMode.conversation,
        context_id="baseline",
    )
    assert state.session.session_id == "s"
    assert state.conversation_brief.schema_version == "conversation_brief.v1"
    assert state.conversation_state.closure_readiness == "not_ready"

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    assert config.memory_key == CONVERSATION_SIMPLE_MEMORY_KEY
    assert config.recent_dialogue_key == CONVERSATION_SIMPLE_RECENT_DIALOGUE_KEY
    assert config.traces_key == CONVERSATION_SIMPLE_TRACES_KEY


def test_canonical_state_roundtrip_preserves_closure_readiness_default() -> None:
    state = build_default_conversation_simple_canonical_state(
        session_id="s2",
        user_id="u2",
        thread_mode=ThreadMode.conversation,
        context_id="baseline",
    )
    payload = state.model_dump(mode="json")
    restored = ConversationSimpleCanonicalState.model_validate(payload)
    assert restored.conversation_state.closure_readiness == "not_ready"
    assert restored.ui_state.finish_button_armed is False


def test_brain_output_schema_exposes_closure_readiness_contract() -> None:
    schema = BrainOutput.model_json_schema()
    conversation_state_props = (
        schema.get("$defs", {})
        .get("ConversationSimpleConversationState", {})
        .get("properties", {})
    )
    assert "closure_readiness" in conversation_state_props
    assert conversation_state_props["closure_readiness"]["default"] == "not_ready"
    assert conversation_state_props["closure_readiness"]["type"] == "string"


def test_turn_context_factory_uses_bound_context() -> None:
    session_state = SessionState(user_id="u", session_id="s")
    session_state.world_state["conversacion_simple_context"] = {
        "flow_id": "conversacion_simple",
        "context_id": "baseline",
        "context_version": "1.0.0",
    }
    turn_context = build_conversacion_simple_turn_context(
        state=session_state,
        entrypoint="/tests",
        requested_context_id="baseline",
    )
    assert turn_context.effective_context_id == "baseline"
    assert turn_context.flow_id == "conversacion_simple"
