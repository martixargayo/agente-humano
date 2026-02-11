from __future__ import annotations

from typing import Any, Dict, Tuple
import warnings


def gate_phase_policy(
    world_diff: Dict[str, Any],
    intent_transition_present: bool,
    loop_flags_changed_flag: bool,
    allowed_ids_hash_changed: bool,
    turn_count: int,
    last_refresh_turn: int,
    interval: int = 2,
) -> Tuple[bool, str, Dict[str, Any]]:
    warnings.warn(
        "gating.gate_planner.gate_phase_policy is deprecated; use legacy.gating_deprecated.",
        DeprecationWarning,
        stacklevel=2,
    )
    from ..legacy.gating_deprecated import gate_phase_policy as legacy_gate_phase_policy

    return legacy_gate_phase_policy(
        world_diff,
        intent_transition_present,
        loop_flags_changed_flag,
        allowed_ids_hash_changed,
        turn_count,
        last_refresh_turn,
        interval=interval,
    )
