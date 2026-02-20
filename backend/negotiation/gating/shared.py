from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

from ..perception.input_shape import (
    ConversationMode,
    VoiceModality,
    input_shape_changed_materially,
    input_shape_features,
)


def critical_world_flags() -> set[str]:
    return set()


def _split_world_diff(world_diff: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if "domain" in world_diff or "interaction" in world_diff:
        domain = world_diff.get("domain", {}) or {}
        interaction = world_diff.get("interaction", {}) or {}
        return domain, interaction
    return world_diff, {}


def interaction_strong_delta_from_diff(
    interaction_diff: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    if not interaction_diff:
        return False, {}
    meta: Dict[str, Any] = {}
    esc = interaction_diff.get("escalation_signal")
    if esc and esc.get("before") != esc.get("after") and esc.get("after") in {"up", "down"}:
        meta["escalation_change"] = {"before": esc.get("before"), "after": esc.get("after")}
        return True, meta
    loop = interaction_diff.get("loop_hint")
    if loop and loop.get("before") is False and loop.get("after") is True:
        meta["loop_enter"] = True
        return True, meta
    return False, meta


def select_policy_id_on_skip(
    last_policy_chosen: str,
    allowed_policy_ids: list[str],
    policy_attempts: Dict[str, int] | None,
    loop_flags: Iterable[str],
    safe_neutral_policy_id: str,
    max_attempts: int = 3,
) -> Tuple[str, str]:
    if not allowed_policy_ids:
        return safe_neutral_policy_id, "no_allowed"
    attempts = dict(policy_attempts or {})
    for policy_id in allowed_policy_ids:
        if attempts.get(policy_id, 0) < max_attempts:
            return policy_id, "first_under_cap"
    if safe_neutral_policy_id in allowed_policy_ids:
        return safe_neutral_policy_id, "fallback_safe_neutral"
    return allowed_policy_ids[0], "fallback_first"
