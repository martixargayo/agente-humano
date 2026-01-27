# backend/negotiation/validation.py
from __future__ import annotations

import os
from typing import Dict, Iterable, List, Tuple

from .schemas import (
    BeliefState,
    InteractionHealth,
    IntentState,
    IntentStatus,
    IntentType,
    NegotiationPhase,
    PolicyDecision,
    PhaseState,
    ProgressState,
    RiskPosture,
    ToneSignal,
    WorldState,
    default_belief_state,
    default_intent_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)


_ALLOWED_HEALTH: set[InteractionHealth] = {"stable", "tense", "stalled"}
_ALLOWED_RISK: set[RiskPosture] = {"low", "mid", "high"}
_ALLOWED_TONE: set[ToneSignal] = {"neutral", "friendly", "tense"}
_ALLOWED_INTENT_STATUS: set[IntentStatus] = {"inactive", "active", "succeeded", "abandoned"}
_ALLOWED_INTENT_TYPES: set[IntentType] = {
    "info_extract",
    "relationship",
    "concession",
    "closing",
    "credibility_check",
}
_ALLOWED_PHASES: set[NegotiationPhase] = {
    "opening",
    "discovery",
    "bargaining",
    "closing",
    "recovery",
}
_ALLOWED_REASON_KEYS = {
    "price_signal",
    "deadline_signal",
    "other_buyer_signal",
    "concession_signal",
    "docs_signal",
    "tone_signal",
}
_STRICT_NORMALIZATION = os.getenv("STRICT_NORMALIZATION") == "1"


def _clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _coerce_str_list(values: object, max_items: int | None = None) -> List[str]:
    if not isinstance(values, list):
        return []
    cleaned = [str(item).strip() for item in values if str(item).strip()]
    if max_items is not None:
        return cleaned[:max_items]
    return cleaned


def _unique_list(values: Iterable[str], max_items: int | None = None) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if max_items is not None and len(result) >= max_items:
            break
    return result


def normalize_world_state(raw: object) -> Tuple[WorldState, List[str]]:
    base = default_world_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("world_state_no_dict")
        return base, issues
    if "tone_signal" not in raw:
        issues.append("tone_signal_missing")
        if _STRICT_NORMALIZATION:
            return base, issues

    base["price_mentioned"] = bool(raw.get("price_mentioned", base["price_mentioned"]))
    price_value = raw.get("price_value", base["price_value"])
    if price_value is None:
        base["price_value"] = None
    else:
        base["price_value"] = _coerce_float(price_value, 0.0)

    base["deadline_claimed"] = bool(raw.get("deadline_claimed", base["deadline_claimed"]))
    base["deadline_text"] = str(raw.get("deadline_text", base["deadline_text"])).strip()
    base["other_buyer_claimed"] = bool(raw.get("other_buyer_claimed", base["other_buyer_claimed"]))
    base["other_buyer_text"] = str(raw.get("other_buyer_text", base["other_buyer_text"])).strip()
    other_offer = raw.get("other_buyer_offer_price", base["other_buyer_offer_price"])
    if other_offer is None:
        base["other_buyer_offer_price"] = None
    else:
        base["other_buyer_offer_price"] = _coerce_float(other_offer, 0.0)
    base["other_buyer_timing_text"] = str(
        raw.get("other_buyer_timing_text", base["other_buyer_timing_text"])
    ).strip()
    base["concession_made"] = bool(raw.get("concession_made", base["concession_made"]))
    base["concession_text"] = str(raw.get("concession_text", base["concession_text"])).strip()
    base["docs_claimed"] = bool(raw.get("docs_claimed", base["docs_claimed"]))
    base["docs_types"] = _unique_list(_coerce_str_list(raw.get("docs_types", [])))
    base["batna_claimed"] = bool(raw.get("batna_claimed", base["batna_claimed"]))
    base["batna_text"] = str(raw.get("batna_text", base["batna_text"])).strip()
    base["urgency_claimed"] = bool(raw.get("urgency_claimed", base["urgency_claimed"]))
    base["urgency_text"] = str(raw.get("urgency_text", base["urgency_text"])).strip()
    base["min_price_claimed"] = bool(raw.get("min_price_claimed", base["min_price_claimed"]))
    base["min_price_text"] = str(raw.get("min_price_text", base["min_price_text"])).strip()
    base["price_firm"] = bool(raw.get("price_firm", base["price_firm"]))
    base["price_firm_text"] = str(raw.get("price_firm_text", base["price_firm_text"])).strip()
    base["evidence_offered"] = bool(raw.get("evidence_offered", base["evidence_offered"]))
    base["evidence_text"] = str(raw.get("evidence_text", base["evidence_text"])).strip()
    base["message_is_vague"] = bool(raw.get("message_is_vague", base["message_is_vague"]))

    tone_signal = raw.get("tone_signal", base["tone_signal"])
    if tone_signal not in _ALLOWED_TONE:
        issues.append("tone_signal_invalid")
        tone_signal = base["tone_signal"]
    base["tone_signal"] = tone_signal

    tone_markers = _coerce_str_list(raw.get("tone_marker_hits", []), max_items=10)
    base["tone_marker_hits"] = _unique_list(tone_markers, max_items=10)

    return base, issues


def normalize_belief_state(
    raw: object,
    previous: BeliefState | None = None,
) -> Tuple[BeliefState, List[str]]:
    base = default_belief_state()
    if previous:
        base.update(previous)
    issues: List[str] = []

    if not isinstance(raw, dict):
        issues.append("belief_state_no_dict")
        return base, issues

    stance = raw.get("stance", {})
    if not isinstance(stance, dict):
        issues.append("stance_invalid")
        stance = {}
    base["stance"]["deal_feasibility"] = _clamp(
        _coerce_float(stance.get("deal_feasibility", base["stance"]["deal_feasibility"]),
                      base["stance"]["deal_feasibility"])
    )
    base["stance"]["seller_flexibility"] = _clamp(
        _coerce_float(stance.get("seller_flexibility", base["stance"]["seller_flexibility"]),
                      base["stance"]["seller_flexibility"])
    )

    reasons_raw = raw.get("reasons", {})
    reasons: Dict[str, Dict[str, object]] = {}
    if isinstance(reasons_raw, dict):
        scored_reasons: List[Tuple[str, Dict[str, object], float]] = []
        for key, value in reasons_raw.items():
            if key not in _ALLOWED_REASON_KEYS:
                issues.append(f"reason_key_invalid:{key}")
                continue
            if not isinstance(value, dict):
                issues.append(f"reason_invalid:{key}")
                continue
            weight = _clamp(_coerce_float(value.get("weight", 0.5), 0.5))
            confidence = _clamp(_coerce_float(value.get("confidence", 0.5), 0.5))
            evidence = str(value.get("evidence", "")).strip()
            if not evidence:
                issues.append(f"reason_missing_evidence:{key}")
            scored_reasons.append(
                (
                    str(key),
                    {
                        "weight": weight,
                        "confidence": confidence,
                        "evidence": evidence,
                    },
                    weight * confidence,
                )
            )
        scored_reasons.sort(key=lambda item: item[2], reverse=True)
        if len(scored_reasons) > 6:
            issues.append("reasons_trimmed")
        for key, payload, _score in scored_reasons[:6]:
            reasons[key] = payload
    else:
        issues.append("reasons_invalid")
    base["reasons"] = reasons

    hypotheses = _coerce_str_list(raw.get("hypotheses", []), max_items=5)
    if len(hypotheses) >= 5:
        issues.append("hypotheses_trimmed")
    base["hypotheses"] = hypotheses

    dynamics = raw.get("dynamics", {})
    if not isinstance(dynamics, dict):
        issues.append("dynamics_invalid")
        dynamics = {}
    interaction_health = dynamics.get("interaction_health", base["dynamics"]["interaction_health"])
    if interaction_health not in _ALLOWED_HEALTH:
        issues.append("interaction_health_invalid")
        interaction_health = base["dynamics"]["interaction_health"]
    base["dynamics"]["interaction_health"] = interaction_health
    base["dynamics"]["last_update_evidence"] = str(
        dynamics.get("last_update_evidence", base["dynamics"]["last_update_evidence"])
    ).strip()

    tom = raw.get("tom", {})
    if not isinstance(tom, dict):
        issues.append("tom_invalid")
        tom = {}
    base["tom"]["seller_goals"] = _coerce_str_list(tom.get("seller_goals", []))
    base["tom"]["seller_tactics"] = _coerce_str_list(tom.get("seller_tactics", []))
    base["tom"]["seller_belief_about_me"] = _coerce_str_list(tom.get("seller_belief_about_me", []))
    base["tom"]["confidence"] = _clamp(
        _coerce_float(tom.get("confidence", base["tom"]["confidence"]), base["tom"]["confidence"])
    )

    return base, issues


def normalize_policy_decision(
    raw: object,
    allowed_policy_ids: Iterable[str],
) -> Tuple[PolicyDecision, List[str]]:
    base = default_policy_decision()
    issues: List[str] = []
    allowed = set(allowed_policy_ids)

    if not isinstance(raw, dict):
        issues.append("policy_decision_no_dict")
        return base, issues

    policy_id = raw.get("policy_id", "")
    if policy_id not in allowed:
        issues.append("policy_id_invalid")
        return base, issues
    base["policy_id"] = str(policy_id)

    base["reason"] = str(raw.get("reason", base["reason"])).strip()[:180]
    base["micro_goal"] = str(raw.get("micro_goal", base["micro_goal"])).strip()[:140]

    risk_posture = raw.get("risk_posture", base["risk_posture"])
    if risk_posture not in _ALLOWED_RISK:
        issues.append("risk_posture_invalid")
        risk_posture = base["risk_posture"]
    base["risk_posture"] = risk_posture

    return base, issues


def normalize_progress_state(raw: object) -> Tuple[ProgressState, List[str]]:
    base = default_progress_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("progress_state_no_dict")
        return base, issues

    last_executed_policy_id = raw.get("last_executed_policy_id", raw.get("last_policy_id", ""))
    base["last_executed_policy_id"] = str(
        last_executed_policy_id or base["last_executed_policy_id"]
    )
    last_outcome = raw.get(
        "last_executed_policy_outcome",
        raw.get("last_policy_outcome", base["last_executed_policy_outcome"]),
    )
    if last_outcome not in {"good", "neutral", "bad", ""}:
        issues.append("policy_outcome_invalid")
        last_outcome = base["last_executed_policy_outcome"]
    base["last_executed_policy_outcome"] = last_outcome

    last_chosen_policy_id = raw.get("last_chosen_policy_id", raw.get("last_policy_id", ""))
    base["last_chosen_policy_id"] = str(
        last_chosen_policy_id or base["last_chosen_policy_id"]
    )

    policy_last_outcome = raw.get("policy_last_outcome", {})
    if isinstance(policy_last_outcome, dict):
        sanitized: Dict[str, str] = {}
        for key, value in policy_last_outcome.items():
            if value not in {"good", "neutral", "bad", ""}:
                issues.append(f"policy_last_outcome_invalid:{key}")
                continue
            sanitized[str(key)] = value
        base["policy_last_outcome"] = sanitized
    else:
        issues.append("policy_last_outcome_invalid")

    attempts = raw.get("policy_attempts", {})
    if isinstance(attempts, dict):
        sanitized_attempts: Dict[str, int] = {}
        for key, value in attempts.items():
            try:
                sanitized_attempts[str(key)] = int(value)
            except (TypeError, ValueError):
                issues.append(f"policy_attempts_invalid_value:{key}")
        base["policy_attempts"] = sanitized_attempts
    else:
        issues.append("policy_attempts_invalid")

    base["loop_flags"] = _unique_list(_coerce_str_list(raw.get("loop_flags", [])))
    base["turns_in_same_mode"] = int(raw.get("turns_in_same_mode", base["turns_in_same_mode"]))
    base["intent_state"], intent_issues = normalize_intent_state(raw.get("intent_state", {}))
    issues.extend(intent_issues)
    base["phase_state"], phase_issues = normalize_phase_state(raw.get("phase_state", {}))
    issues.extend(phase_issues)

    return base, issues


def normalize_phase_state(raw: object) -> Tuple[PhaseState, List[str]]:
    base = default_progress_state()["phase_state"]
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("phase_state_no_dict")
        return base, issues

    phase = raw.get("phase", base["phase"])
    if phase not in _ALLOWED_PHASES:
        issues.append("phase_invalid")
        phase = "opening"
    base["phase"] = phase

    base["confidence"] = _clamp(
        _coerce_float(raw.get("confidence", base["confidence"]), base["confidence"])
    )

    reasons = _unique_list(_coerce_str_list(raw.get("reasons", []), max_items=8), max_items=8)
    base["reasons"] = reasons

    last_updated_turn = raw.get("last_updated_turn", base["last_updated_turn"])
    try:
        base["last_updated_turn"] = max(0, int(last_updated_turn))
    except (TypeError, ValueError):
        issues.append("phase_last_updated_invalid")
        base["last_updated_turn"] = 0

    return base, issues


def _normalize_slots(raw: object) -> Tuple[dict, List[str]]:
    issues: List[str] = []
    slots = {
        "slots_required": [],
        "slots_optional": [],
        "slots_filled": {},
    }
    if not isinstance(raw, dict):
        issues.append("intent_slots_invalid")
        return slots, issues

    slots["slots_required"] = _unique_list(_coerce_str_list(raw.get("slots_required", [])))
    slots["slots_optional"] = _unique_list(_coerce_str_list(raw.get("slots_optional", [])))

    filled_raw = raw.get("slots_filled", {})
    if isinstance(filled_raw, dict):
        filled: Dict[str, dict] = {}
        for key, value in filled_raw.items():
            if not isinstance(value, dict):
                issues.append(f"intent_slot_invalid:{key}")
                continue
            filled[str(key)] = {
                "value": value.get("value"),
                "evidence": str(value.get("evidence", "")).strip(),
                "confidence": _clamp(_coerce_float(value.get("confidence", 0.5), 0.5)),
            }
        slots["slots_filled"] = filled
    else:
        issues.append("intent_slots_filled_invalid")

    return slots, issues


def _normalize_steps(raw: object) -> Tuple[List[dict], List[str]]:
    issues: List[str] = []
    steps: List[dict] = []
    if not isinstance(raw, list):
        return steps, ["intent_steps_invalid"]

    legacy_map = {
        "ask_open": "probe_open",
        "narrow": "probe_narrow",
        "validate": "request_evidence",
        "leverage": "trade_incentive",
        "deescalate": "pressure_soft",
        "rebuild": "probe_open",
        "advance": "close_next",
        "probe": "probe_open",
        "tradeoff": "trade_incentive",
        "close": "close_next",
        "summarize": "probe_narrow",
        "confirm_terms": "close_next",
        "ask_evidence": "request_evidence",
        "probe_details": "probe_narrow",
    }

    for idx, item in enumerate(raw):
        if isinstance(item, str):
            kind = legacy_map.get(item, "probe_open")
            steps.append(
                {
                    "kind": kind,
                    "target_slot": "unknown",
                    "success_if_filled": ["unknown"],
                }
            )
            issues.append(f"intent_step_legacy:{idx}")
            continue
        if not isinstance(item, dict):
            issues.append(f"intent_step_invalid:{idx}")
            continue
        kind = str(item.get("kind", "")).strip()
        target_slot = str(item.get("target_slot", "")).strip()
        success_if_filled = _unique_list(_coerce_str_list(item.get("success_if_filled", [])))
        if not kind or not target_slot or not success_if_filled:
            issues.append(f"intent_step_missing_fields:{idx}")
            continue
        steps.append(
            {
                "kind": kind,
                "target_slot": target_slot,
                "success_if_filled": success_if_filled,
            }
        )
    return steps[:5], issues


def normalize_intent_state(raw: object) -> Tuple[IntentState, List[str]]:
    base = default_intent_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("intent_state_no_dict")
        return base, issues

    status = raw.get("status", base["status"])
    if status not in _ALLOWED_INTENT_STATUS:
        issues.append("intent_status_invalid")
        status = base["status"]
    base["status"] = status

    intent_type = raw.get("intent_type", base["intent_type"])
    if intent_type not in _ALLOWED_INTENT_TYPES:
        issues.append("intent_type_invalid")
        intent_type = base["intent_type"]
    base["intent_type"] = intent_type

    base["intent_goal"] = str(raw.get("intent_goal", base["intent_goal"])).strip()
    steps, step_issues = _normalize_steps(raw.get("steps", []))
    if step_issues:
        issues.extend(step_issues)
    base["steps"] = steps
    base["step_idx"] = int(raw.get("step_idx", base["step_idx"]))
    base["step_attempts"] = int(raw.get("step_attempts", base["step_attempts"]))
    base["max_attempts_per_step"] = max(
        1, int(raw.get("max_attempts_per_step", base["max_attempts_per_step"]))
    )
    base["success_criteria"] = _unique_list(
        _coerce_str_list(raw.get("success_criteria", []), max_items=5)
    )

    slots, slot_issues = _normalize_slots(raw.get("slots", {}))
    base["slots"] = slots
    issues.extend(slot_issues)

    base["confidence"] = _clamp(_coerce_float(raw.get("confidence", base["confidence"]),
                                              base["confidence"]))
    base["created_turn"] = int(raw.get("created_turn", base["created_turn"]))
    base["last_turn"] = int(raw.get("last_turn", base["last_turn"]))
    base["continue_until"] = str(raw.get("continue_until", base["continue_until"])).strip()
    base["abandon_reasons"] = _unique_list(_coerce_str_list(raw.get("abandon_reasons", [])))
    base["last_observation"] = str(raw.get("last_observation", base["last_observation"])).strip()
    base["next_action_hint"] = str(raw.get("next_action_hint", base["next_action_hint"])).strip()

    if base["status"] == "active":
        if not base["steps"]:
            issues.append("intent_steps_missing")
        if base["steps"]:
            max_idx = len(base["steps"]) - 1
            if base["step_idx"] < 0 or base["step_idx"] > max_idx:
                issues.append("intent_step_idx_invalid")
                base["step_idx"] = min(max(base["step_idx"], 0), max_idx)
        else:
            base["step_idx"] = 0

    return base, issues
