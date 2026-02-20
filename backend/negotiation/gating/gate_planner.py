from __future__ import annotations

from typing import Any, Dict, Tuple


def gate_phase_policy(
    world_diff: Dict[str, Any],
    plan_signal_present: bool = False,
    loop_flags_changed_flag: bool = False,
    allowed_ids_hash_changed: bool = False,
    turn_count: int = 0,
    last_refresh_turn: int = 0,
    interval: int = 2,
    **kwargs: Any,
) -> Tuple[bool, str, Dict[str, Any]]:
    if last_refresh_turn == 0:
        return False, "initial_refresh", {"path": "initial"}

    interval_expired = (turn_count - last_refresh_turn) >= interval
    has_world_delta = bool(world_diff)
    if not has_world_delta and not plan_signal_present and not loop_flags_changed_flag and not allowed_ids_hash_changed and not interval_expired:
        return True, "no_delta_interval_hold", {"path": "hold"}
    if interval_expired:
        return False, "interval_expired", {"path": "refresh"}
    return False, "delta_or_signal", {"path": "refresh"}
