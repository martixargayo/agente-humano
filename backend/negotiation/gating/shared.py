from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

from ..perception.input_shape import (
    ConversationMode,
    VoiceModality,
    input_shape_changed_materially,
    input_shape_features,
)


def critical_world_flags() -> set[str]:
    return {
        "price_mentioned",
        "deadline_claimed",
        "other_buyer_claimed",
        "concession_made",
        "docs_claimed",
        "batna_claimed",
        "urgency_claimed",
        "min_price_claimed",
        "price_firm",
        "evidence_offered",
    }


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
    attempts = policy_attempts or {}
    loop_flags_clean = not list(loop_flags)
    if (
        last_policy_chosen
        and last_policy_chosen in allowed_policy_ids
        and loop_flags_clean
        and attempts.get(last_policy_chosen, 0) < max_attempts
    ):
        return last_policy_chosen, "reuse_last_policy"
    if safe_neutral_policy_id in allowed_policy_ids:
        return safe_neutral_policy_id, "safe_neutral_fallback"
    fallback = allowed_policy_ids[0] if allowed_policy_ids else safe_neutral_policy_id
    return fallback, "safe_neutral_missing"
