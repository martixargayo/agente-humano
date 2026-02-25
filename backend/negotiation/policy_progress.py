from __future__ import annotations

from .schemas import default_policy_state


def update_policy_state(
    prev_policy_state: dict | None,
    world_state: dict,
    world_diff: dict,
    belief_state: dict,
    belief_diff: dict,
    progress_state: dict,
    user_message: str,
    turn_count: int,
    **_: dict,
) -> tuple[dict, dict, dict]:
    del world_state, world_diff, belief_state, belief_diff, user_message
    policy_state = default_policy_state()
    if isinstance(prev_policy_state, dict):
        policy_state.update(prev_policy_state)
    policy_state["last_turn"] = turn_count
    if policy_state.get("started_turn", 0) == 0:
        policy_state["started_turn"] = turn_count
    policy_state["planner_request"] = "replan"
    progress_state["policy_state"] = policy_state
    hint = {
        "policy_active": True,
        "policy_id": str(policy_state.get("policy_id", "semantic_ledger")),
        "next_action_hint": "",
    }
    meta = {
        "transition": "semantic_bridge",
        "reasons": ["bridge_inocuo_semantic_runtime"],
    }
    return policy_state, hint, meta
