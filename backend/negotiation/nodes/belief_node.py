from __future__ import annotations

from ..schemas import default_belief_state
from .world_node import flush_world_parallel_pending


def belief_updater_node(state: dict) -> dict:
    flush_world_parallel_pending(state)
    if not isinstance(state.get("belief_state"), dict):
        state["belief_state"] = default_belief_state()
    if not isinstance(state.get("prev_belief_state"), dict):
        state["prev_belief_state"] = default_belief_state()
    state["belief_diff"] = {}
    return state
