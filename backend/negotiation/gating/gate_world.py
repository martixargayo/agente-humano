from __future__ import annotations

from typing import Any, Dict, Tuple

from .shared import input_shape_changed_materially


_STRONG_INTERACTION_FIELDS_FOR_WORLD = {
    "implicit_acceptance",
    "escalation_signal",
    "loop_hint",
    "evasion_detected",
}


def _fingerprint_changed_fields(
    prev_fp: Dict[str, Any] | None, curr_fp: Dict[str, Any] | None
) -> list[str]:
    prev_fp = prev_fp or {}
    curr_fp = curr_fp or {}
    keys = set(prev_fp.keys()) | set(curr_fp.keys())
    out = []
    for k in keys:
        if prev_fp.get(k) != curr_fp.get(k):
            out.append(k)
    return out


def gate_world(
    user_message: str,
    turn_count: int,
    last_refresh_turn: int,
    prev_features: Dict[str, Any] | None,
    current_features: Dict[str, Any],
    interaction_fingerprint_prev: Dict[str, Any] | None = None,
    interaction_fingerprint_current: Dict[str, Any] | None = None,
    interaction_fingerprint_version: int = 1,
    interval: int = 3,
    modality: str = "text",
    conversation_mode: str = "general",
) -> Tuple[bool, str, Dict[str, Any]]:
    if not (user_message or "").strip():
        return True, "empty_message", {"extractor_mode": "none"}
    interval_expired = (turn_count - last_refresh_turn) >= interval
    changed, changed_keys = input_shape_changed_materially(
        prev_features,
        current_features,
        modality=modality,
        conversation_mode=conversation_mode,
    )
    interaction_changed = False
    interaction_changed_fields: list[str] = []
    if interaction_fingerprint_prev is not None and interaction_fingerprint_current is not None:
        interaction_changed = interaction_fingerprint_prev != interaction_fingerprint_current
        interaction_changed_fields = _fingerprint_changed_fields(
            interaction_fingerprint_prev, interaction_fingerprint_current
        )
    interaction_strong_for_world = any(
        f in _STRONG_INTERACTION_FIELDS_FOR_WORLD for f in interaction_changed_fields
    )
    change_meta: Dict[str, Any] = {
        "changed_keys": changed_keys,
        "interaction_changed": interaction_changed,
        "interaction_changed_fields": interaction_changed_fields,
        "interaction_fingerprint_version": interaction_fingerprint_version,
        "interaction_fingerprint_current": interaction_fingerprint_current or {},
        "modality": modality,
        "conversation_mode": conversation_mode,
    }
    if interval_expired:
        change_meta["extractor_mode"] = "llm"
        return False, "interval_expired", change_meta
    if changed:
        change_meta["extractor_mode"] = "llm"
        return False, "input_shape_changed", change_meta
    if interaction_strong_for_world:
        change_meta["extractor_mode"] = "llm"
        return False, "interaction_changed", change_meta
    change_meta["extractor_mode"] = "none"
    return True, "interval_hold", change_meta
