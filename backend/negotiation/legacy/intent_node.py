from __future__ import annotations

from .intent_manager import update_intent_state


def intent_manager_node(state: dict) -> dict:
    intent_state, intent_meta, intent_hint = update_intent_state(
        prev_intent=state.get("progress_state", {}).get("intent_state"),
        prev_world_state=state.get("prev_world_state"),
        world_state=state["world_state"],
        belief_state=state["belief_state"],
        progress_state=state["progress_state"],
        user_message=state.get("user_message", ""),
        turn_count=state.get("turn_count", 0),
    )
    state["progress_state"]["intent_state"] = intent_state
    state["intent_hint"] = intent_hint
    state["intent_meta"] = intent_meta
    return state
