from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, Tuple


_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_PATTERN = re.compile(r"\b\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}\b")
_SYMBOL_PATTERN = re.compile(r"[%€$@#\+\-]")


def stable_allowed_ids_hash(allowed_ids: Iterable[str]) -> str:
    joined = "|".join(sorted(set(allowed_ids)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _length_bucket(length: int) -> str:
    if length <= 20:
        return "xs"
    if length <= 80:
        return "s"
    if length <= 200:
        return "m"
    if length <= 400:
        return "l"
    return "xl"


def input_shape_features(text: str) -> Dict[str, Any]:
    raw = text or ""
    length = len(raw)
    non_alpha = sum(1 for ch in raw if not ch.isalpha())
    non_alpha_ratio = 0.0 if length == 0 else non_alpha / max(length, 1)
    has_digit = any(ch.isdigit() for ch in raw)
    has_symbol = bool(_SYMBOL_PATTERN.search(raw))
    has_email = bool(_EMAIL_PATTERN.search(raw))
    has_phone = bool(_PHONE_PATTERN.search(raw))
    has_currency = any(sym in raw for sym in ("€", "$", "%"))
    return {
        "length": length,
        "length_bucket": _length_bucket(length),
        "non_alpha_ratio": round(non_alpha_ratio, 4),
        "has_digit": has_digit,
        "has_symbol": has_symbol,
        "has_email": has_email,
        "has_phone": has_phone,
        "has_currency": has_currency,
    }


def input_shape_changed_materially(
    prev_features: Dict[str, Any] | None,
    current_features: Dict[str, Any],
    length_delta_ratio_threshold: float = 0.35,
    non_alpha_ratio_threshold: float = 0.20,
) -> Tuple[bool, Dict[str, Any]]:
    if not prev_features:
        return True, {"reason": "no_prev_features"}

    prev_len = int(prev_features.get("length", 0) or 0)
    curr_len = int(current_features.get("length", 0) or 0)
    length_delta_ratio = (
        abs(curr_len - prev_len) / max(prev_len, 1)
        if prev_len > 0
        else (1.0 if curr_len > 0 else 0.0)
    )
    prev_non_alpha = float(prev_features.get("non_alpha_ratio", 0.0) or 0.0)
    curr_non_alpha = float(current_features.get("non_alpha_ratio", 0.0) or 0.0)
    non_alpha_delta = abs(curr_non_alpha - prev_non_alpha)

    length_bucket_changed = (
        prev_features.get("length_bucket") != current_features.get("length_bucket")
    )
    digit_or_symbol_changed = any(
        bool(prev_features.get(key)) != bool(current_features.get(key))
        for key in (
            "has_digit",
            "has_symbol",
            "has_email",
            "has_phone",
            "has_currency",
        )
    )

    changed = (
        length_delta_ratio >= length_delta_ratio_threshold
        or non_alpha_delta >= non_alpha_ratio_threshold
        or length_bucket_changed
        or digit_or_symbol_changed
    )
    return changed, {
        "length_delta_ratio": round(length_delta_ratio, 4),
        "non_alpha_ratio_delta": round(non_alpha_delta, 4),
        "length_bucket_changed": length_bucket_changed,
        "digit_or_symbol_changed": digit_or_symbol_changed,
    }


def precedence_signature(precedence: Dict[str, Any] | None) -> str:
    prec = precedence or {}
    min_tags = ",".join(sorted(prec.get("min_policy_tags") or []))
    block_tags = ",".join(sorted(prec.get("block_policy_tags") or []))
    return "|".join(
        [
            str(prec.get("mode", "")),
            str(prec.get("phase_floor", "")),
            str(bool(prec.get("allow_closing", True))),
            min_tags,
            block_tags,
        ]
    )


def loop_flags_changed(prev_flags: Iterable[str], current_flags: Iterable[str]) -> bool:
    return sorted(set(prev_flags)) != sorted(set(current_flags))


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


def gate_world(
    user_message: str,
    turn_count: int,
    last_refresh_turn: int,
    prev_features: Dict[str, Any] | None,
    current_features: Dict[str, Any],
    interval: int = 3,
) -> Tuple[bool, str, Dict[str, Any]]:
    if not (user_message or "").strip():
        return True, "empty_message", {}
    interval_expired = (turn_count - last_refresh_turn) >= interval
    changed, change_meta = input_shape_changed_materially(prev_features, current_features)
    if interval_expired or changed:
        reason = "interval_expired" if interval_expired else "input_shape_changed"
        return False, reason, change_meta
    return True, "interval_hold", change_meta


def gate_belief(
    world_diff: Dict[str, Any],
    prev_world: Dict[str, Any],
    world: Dict[str, Any],
    turn_count: int,
    last_refresh_turn: int,
    interval: int = 3,
) -> Tuple[bool, str]:
    if last_refresh_turn == 0:
        return False, "initial_refresh"
    world_diff_empty = not bool(world_diff)
    critical_change = any(
        prev_world.get(flag) != world.get(flag) for flag in critical_world_flags()
    )
    tone_change = prev_world.get("tone_signal") != world.get("tone_signal")
    interval_expired = (turn_count - last_refresh_turn) >= interval
    if world_diff_empty and not critical_change and not tone_change and not interval_expired:
        return True, "no_delta_interval_hold"
    reason = "interval_expired" if interval_expired else "delta_or_signal"
    return False, reason


def gate_phase_policy(
    world_diff: Dict[str, Any],
    precedence_changed: bool,
    intent_transition_present: bool,
    loop_flags_changed_flag: bool,
    allowed_ids_hash_changed: bool,
    turn_count: int,
    last_refresh_turn: int,
    interval: int = 2,
) -> Tuple[bool, str]:
    critical_diff = any(key in world_diff for key in critical_world_flags())
    strong_signals = (
        critical_diff
        or precedence_changed
        or intent_transition_present
        or loop_flags_changed_flag
        or allowed_ids_hash_changed
    )
    interval_expired = (turn_count - last_refresh_turn) >= interval
    if interval_expired or strong_signals:
        reason = "interval_expired" if interval_expired else "strong_signals"
        return False, reason
    return True, "interval_hold"


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
