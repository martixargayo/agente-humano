from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple
import warnings

from ..perception.input_shape import (
    ConversationMode,
    VoiceModality,
    input_shape_changed_materially,
    input_shape_features,
)
from ..specs.world_keys import ALLOWED_NEGOTIATION_DOMAIN_KEYS


def critical_world_flags() -> set[str]:
    return set(ALLOWED_NEGOTIATION_DOMAIN_KEYS) | {"message_is_vague"}


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
    ia = interaction_diff.get("implicit_acceptance")
    if ia and ia.get("before") is False and ia.get("after") is True:
        meta["implicit_acceptance_rise"] = True
        return True, meta
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
    warnings.warn(
        "gating.shared.select_policy_id_on_skip is deprecated; use legacy.gating_deprecated.",
        DeprecationWarning,
        stacklevel=2,
    )
    from ..legacy.gating_deprecated import select_policy_id_on_skip as legacy_select_policy_id

    return legacy_select_policy_id(
        last_policy_chosen,
        allowed_policy_ids,
        policy_attempts,
        loop_flags,
        safe_neutral_policy_id,
        max_attempts=max_attempts,
    )
