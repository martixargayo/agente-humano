from __future__ import annotations

from ..gate_utils import precedence_signature
from ..precedence import compute_precedence


def precedence_node(state: dict) -> dict:
    world_state = state["world_state"]
    belief_state = state["belief_state"]
    precedence_world = {
        "other_buyer_claimed": world_state.get("other_buyer_claimed"),
        "deadline_claimed": world_state.get("deadline_claimed"),
        "price_firm": world_state.get("price_firm"),
        "concession_made": world_state.get("concession_made"),
        "price_mentioned": world_state.get("price_mentioned"),
    }
    precedence_belief = {
        "dynamics": {
            "interaction_health": (belief_state.get("dynamics") or {}).get(
                "interaction_health", "stable"
            )
        }
    }
    prec = compute_precedence(
        world=precedence_world,
        belief=precedence_belief,
        intent=state.get("progress_state", {}).get("intent_state"),
    )
    state["precedence"] = {
        "mode": prec.mode,
        "reason": prec.reason,
        "min_policy_tags": list(prec.min_policy_tags),
        "block_policy_tags": list(prec.block_policy_tags),
        "phase_floor": prec.phase_floor,
        "allow_closing": prec.allow_closing,
    }
    state["precedence_signature"] = precedence_signature(state["precedence"])
    return state
