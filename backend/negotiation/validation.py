from __future__ import annotations

from typing import Any, List, Tuple

from .schemas import (
    BeliefState,
    PhaseState,
    PolicyDecision,
    ProgressState,
    WorldState,
    default_belief_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)


DEFAULT_WORLD_ITEM_CONFIDENCE = 0.6


def clamp01(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out < 0.0:
        return 0.0
    if out > 1.0:
        return 1.0
    return out


def to_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_str_list(values: Any, max_items: int) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values:
        txt = str(item or "").strip()
        if txt:
            out.append(txt)
        if len(out) >= max_items:
            break
    return out


def _unique_list(values: list[str], max_items: int = 40) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= max_items:
            break
    return out


def _normalize_text_key(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def normalize_world_buckets(raw: object, default_turn: int = 0, max_items: int = 8) -> dict:
    src = dict(raw or {}) if isinstance(raw, dict) else {}
    keys = ("offers", "concessions", "constraints", "interests", "claims", "requests", "context")
    out: dict = {k: [] for k in keys}

    for bucket in keys:
        vals = src.get(bucket, []) if isinstance(src.get(bucket), list) else []
        dedup: dict[str, dict] = {}
        for item in vals:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "") or "").strip()[:180]
            raw_text = str(item.get("raw_text", text) or "").strip()[:240]
            if not text or not raw_text:
                continue
            key = _normalize_text_key(raw_text)
            if not key:
                continue
            raw_conf = item.get("confidence", None)
            explicit_defaulted = item.get("confidence_defaulted", None)
            confidence_defaulted = bool(explicit_defaulted) if isinstance(explicit_defaulted, bool) else False
            confidence_source = "emitted_by_llm"
            if raw_conf is None:
                conf = DEFAULT_WORLD_ITEM_CONFIDENCE
                confidence_defaulted = True
                confidence_source = "defaulted_by_normalizer"
            else:
                try:
                    conf = float(raw_conf)
                    if conf <= 0.0:
                        conf = DEFAULT_WORLD_ITEM_CONFIDENCE
                        confidence_defaulted = True
                        confidence_source = "defaulted_by_normalizer"
                except (TypeError, ValueError):
                    conf = DEFAULT_WORLD_ITEM_CONFIDENCE
                    confidence_defaulted = True
                    confidence_source = "defaulted_by_normalizer"
            conf = clamp01(conf, DEFAULT_WORLD_ITEM_CONFIDENCE)
            turn = to_int(item.get("source_turn"), default_turn) or default_turn
            cand = {
                "text": text,
                "raw_text": raw_text,
                "confidence": conf,
                "confidence_defaulted": confidence_defaulted,
                "source_turn": int(turn),
                "confidence_source": confidence_source,
            }
            prev = dedup.get(key)
            if prev is None or float(cand["confidence"]) >= float(prev.get("confidence", 0.0)):
                dedup[key] = cand
        out[bucket] = sorted(dedup.values(), key=lambda d: float(d.get("confidence", 0.0)), reverse=True)[:max_items]
    return out


def _normalize_belief_bucket_item(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text", "") or "").strip()[:180]
    if not text:
        return None
    status = str(raw.get("status", "active") or "active")
    if status not in {"active", "weakening", "new"}:
        status = "active"
    conf = clamp01(raw.get("confidence", 0.0), 0.0)
    return {"text": text, "confidence": conf, "status": status}


def normalize_belief_buckets(raw: object) -> dict:
    src = dict(raw or {}) if isinstance(raw, dict) else {}
    limits = {"hypotheses": 6, "strategy_notes": 3, "risk_flags": 3, "watch_items": 3}
    out: dict = {k: [] for k in limits}
    for bucket, max_items in limits.items():
        vals = src.get(bucket, []) if isinstance(src.get(bucket), list) else []
        dedup: dict[str, dict] = {}
        for it in vals:
            item = _normalize_belief_bucket_item(it)
            if item is None:
                continue
            key = _normalize_text_key(item["text"])
            prev = dedup.get(key)
            if prev is None or float(item.get("confidence", 0.0)) >= float(prev.get("confidence", 0.0)):
                dedup[key] = item
        out[bucket] = sorted(dedup.values(), key=lambda d: float(d.get("confidence", 0.0)), reverse=True)[:max_items]
    return out


def normalize_world_state(raw: object) -> Tuple[WorldState, List[str]]:
    base = default_world_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        return base, ["world_state_no_dict"]

    src = dict(raw)
    meta_in = src.get("world_state_meta") if isinstance(src.get("world_state_meta"), dict) else {}
    turn_idx = to_int(meta_in.get("turn_idx"), 0) or 0

    base["schema_version"] = "v3"
    base["world_buckets"] = normalize_world_buckets(src.get("world_buckets", {}), default_turn=turn_idx, max_items=8)

    meta = dict(base.get("world_state_meta") or {})
    meta["turn_idx"] = int(turn_idx)
    meta["updated_fields"] = _unique_list(_coerce_str_list(meta_in.get("updated_fields", []), 40), max_items=40)
    meta["updated_buckets"] = _unique_list(_coerce_str_list(meta_in.get("updated_buckets", []), 20), max_items=20)
    meta["extractor_failed"] = bool(meta_in.get("extractor_failed", False))
    meta["error"] = str(meta_in.get("error", "") or "")[:200]
    unknown_claims = meta_in.get("unknown_claims", [])
    meta["unknown_claims"] = unknown_claims if isinstance(unknown_claims, list) else []
    base["world_state_meta"] = meta
    return base, issues


def normalize_world_state_v2(raw: object) -> Tuple[dict, List[str]]:
    return normalize_world_state(raw)


def normalize_belief_state(
    raw: object,
    previous: BeliefState | None = None,
) -> Tuple[BeliefState, List[str]]:
    base = default_belief_state()
    if previous and isinstance(previous, dict):
        base.update({k: v for k, v in previous.items() if k in {"schema_version", "belief_buckets", "planner_signals"}})
    issues: List[str] = []
    if not isinstance(raw, dict):
        return base, ["belief_state_no_dict"]

    base["belief_buckets"] = normalize_belief_buckets(raw.get("belief_buckets", base.get("belief_buckets", {})))

    planner_signals = dict(base.get("planner_signals") or {})
    in_signals = raw.get("planner_signals") if isinstance(raw.get("planner_signals"), dict) else {}
    if in_signals:
        planner_signals["interaction_health"] = str(in_signals.get("interaction_health", planner_signals.get("interaction_health", "stable")))
        planner_signals["conflict_risk"] = clamp01(in_signals.get("conflict_risk", planner_signals.get("conflict_risk", 0.0)), 0.0)
        planner_signals["recommended_move"] = str(in_signals.get("recommended_move", planner_signals.get("recommended_move", "hold")))
        planner_signals["recovery_mode"] = bool(in_signals.get("recovery_mode", planner_signals.get("recovery_mode", False)))
    base["planner_signals"] = planner_signals
    base["schema_version"] = "v3"
    return base, issues


def normalize_belief_state_v2(raw: object, previous: BeliefState | None = None) -> Tuple[dict, List[str]]:
    return normalize_belief_state(raw, previous=previous)


def normalize_phase_state(raw: object) -> Tuple[PhaseState, List[str]]:
    base = default_progress_state()["phase_state"]
    issues: List[str] = []
    if not isinstance(raw, dict):
        return base, ["phase_state_no_dict"]
    out = dict(base)
    out["phase"] = str(raw.get("phase", out["phase"]))
    out["phase_proposed"] = str(raw.get("phase_proposed", out["phase_proposed"]))
    out["phase_effective"] = str(raw.get("phase_effective", out["phase_effective"]))
    out["recovery_mode"] = bool(raw.get("recovery_mode", out["recovery_mode"]))
    out["recovery_stable_turns"] = int(raw.get("recovery_stable_turns", out["recovery_stable_turns"]) or 0)
    out["confidence"] = clamp01(raw.get("confidence", out["confidence"]), out["confidence"])
    out["reasons"] = _coerce_str_list(raw.get("reasons", out["reasons"]), 8)
    out["last_updated_turn"] = int(raw.get("last_updated_turn", out["last_updated_turn"]) or 0)
    return out, issues


def normalize_progress_state(raw: object) -> Tuple[ProgressState, List[str]]:
    base = default_progress_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        return base, ["progress_state_no_dict"]
    out = dict(base)
    out.update({k: v for k, v in raw.items() if k in out})

    gate = dict(base.get("gate_state") or {})
    if isinstance(raw.get("gate_state"), dict):
        gate.update(raw.get("gate_state") or {})
    gate["world_meta_fingerprint_prev"] = str(gate.get("world_meta_fingerprint_prev", ""))
    out["gate_state"] = gate

    out["phase_state"], phase_issues = normalize_phase_state(raw.get("phase_state", {}))
    issues.extend(phase_issues)
    return out, issues


def normalize_policy_decision(raw: object, allowed_policy_ids: list[str] | None = None) -> Tuple[PolicyDecision, List[str]]:
    base = default_policy_decision()
    issues: List[str] = []
    if not isinstance(raw, dict):
        return base, ["policy_decision_no_dict"]
    out = dict(base)
    out.update({k: v for k, v in raw.items() if k in out})
    out["policy_id"] = str(out.get("policy_id", "") or "")
    if allowed_policy_ids and out["policy_id"] and out["policy_id"] not in allowed_policy_ids:
        issues.append("policy_id_not_allowed")
        out["policy_id"] = allowed_policy_ids[0] if allowed_policy_ids else base["policy_id"]
    out["reason"] = str(out.get("reason", "") or "")[:240]
    out["micro_goal"] = str(out.get("micro_goal", "") or "")[:240]
    out["why_short"] = str(out.get("why_short", "") or "")[:200]
    out["inputs_used"] = _coerce_str_list(out.get("inputs_used", []), 20)
    return out, issues
