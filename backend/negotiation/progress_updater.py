from __future__ import annotations

from .schemas import (
    BeliefState,
    PolicyDecision,
    ProgressState,
    WorldState,
    default_progress_state,
    default_semantic_ledger,
)


def update_progress_state(
    prev_progress: ProgressState | None,
    policy_decision: PolicyDecision,
    last_policy_executed: PolicyDecision | None,
    prev_world_state: WorldState,
    world_state: WorldState,
    prev_belief_state: BeliefState | None,
    belief_state: BeliefState,
    turn_count: int = 0,
    include_debug: bool = False,
    policy_plan_judgement: dict | None = None,
    user_message: str = "",
    semantic_judge: dict | None = None,
    **_: dict,
) -> ProgressState | tuple[ProgressState, dict]:
    del last_policy_executed, prev_world_state, world_state, prev_belief_state, belief_state
    del policy_plan_judgement, user_message

    progress = default_progress_state()
    if isinstance(prev_progress, dict):
        progress.update(prev_progress)

    semantic_ledger = default_semantic_ledger()
    prev_ledger = progress.get("semantic_ledger") if isinstance(progress.get("semantic_ledger"), dict) else {}
    if isinstance(prev_ledger, dict):
        for key in semantic_ledger:
            val = prev_ledger.get(key)
            if isinstance(val, list):
                semantic_ledger[key] = [str(x).strip()[:180] for x in val if str(x).strip()][:6]

    incoming = (semantic_judge or {}).get("semantic_ledger") if isinstance(semantic_judge, dict) else {}
    if isinstance(incoming, dict):
        for key in semantic_ledger:
            val = incoming.get(key)
            if isinstance(val, list):
                semantic_ledger[key] = [str(x).strip()[:180] for x in val if str(x).strip()][:6]

    progress["semantic_ledger"] = semantic_ledger
    progress["last_chosen_policy_id"] = str((policy_decision or {}).get("policy_id", "semantic_ledger") or "semantic_ledger")
    progress["last_progress_update_turn"] = int(turn_count or 0)

    if not include_debug:
        return progress

    debug = {
        "semantic_ledger": {
            "lo_que_ya_se_toco": list((progress.get("semantic_ledger") or {}).get("lo_que_ya_se_toco", []))[:3],
            "lo_que_ya_pregunte": list((progress.get("semantic_ledger") or {}).get("lo_que_ya_pregunte", []))[:3],
            "lo_que_falta_pero_no_insistire": list((progress.get("semantic_ledger") or {}).get("lo_que_falta_pero_no_insistire", []))[:3],
        },
        "policy_id": progress.get("last_chosen_policy_id", "semantic_ledger"),
    }
    return progress, debug
