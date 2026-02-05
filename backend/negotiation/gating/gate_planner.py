from __future__ import annotations

from typing import Any, Dict, Tuple

from .shared import critical_world_flags, interaction_strong_delta_from_diff, _split_world_diff


def gate_phase_policy(
    world_diff: Dict[str, Any],
    precedence_changed: bool,
    intent_transition_present: bool,
    loop_flags_changed_flag: bool,
    allowed_ids_hash_changed: bool,
    turn_count: int,
    last_refresh_turn: int,
    interval: int = 2,
) -> Tuple[bool, str, Dict[str, Any]]:
    domain_diff, interaction_diff = _split_world_diff(world_diff)
    critical_diff = any(key in domain_diff for key in critical_world_flags())
    interaction_strong, interaction_meta = interaction_strong_delta_from_diff(interaction_diff)
    strong_signals = (
        critical_diff
        or precedence_changed
        or intent_transition_present
        or loop_flags_changed_flag
        or allowed_ids_hash_changed
        or interaction_strong
    )
    interval_expired = (turn_count - last_refresh_turn) >= interval
    if interval_expired or strong_signals:
        reason = "interval_expired" if interval_expired else "strong_signals"
        return False, reason, {"interaction_meta": interaction_meta}
    return True, "interval_hold", {"interaction_meta": interaction_meta}
