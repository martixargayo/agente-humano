from __future__ import annotations

from typing import Any

from .schemas import default_belief_state, default_world_state
from .validation import normalize_belief_buckets, normalize_world_buckets


LEGACY_WORLD_KEYS = {
    "universal_domain",
    "negotiation",
    "universal_state",
    "universal_v2",
    "negotiation_v2",
    "open_claims",
    "evidence_items",
    "world_observations",
    "world_observations_v2",
    "world_derived",
}

LEGACY_BELIEF_KEYS = {
    "universal",
    "negotiation",
    "dynamics",
    "tom",
    "stance",
    "reasons",
    "hypotheses",
    "hypotheses_structural",
    "hypotheses_observational",
    "evaluations",
}


def _to_bucket_item(text: str, confidence: float = 0.6, turn_idx: int = 0) -> dict[str, Any]:
    txt = str(text or "").strip()
    if not txt:
        return {}
    return {
        "text": txt[:180],
        "raw_text": txt[:240],
        "confidence": max(0.0, min(1.0, float(confidence))),
        "source_turn": int(turn_idx or 0),
    }


def migrate_world_state_to_v3(world_state: dict[str, Any] | None) -> dict[str, Any]:
    base = default_world_state()
    src = dict(world_state or {}) if isinstance(world_state, dict) else {}

    turn_idx = int(((src.get("world_state_meta") or {}).get("turn_idx") or 0) if isinstance(src.get("world_state_meta"), dict) else 0)

    buckets = dict(src.get("world_buckets") or {}) if isinstance(src.get("world_buckets"), dict) else {}

    # Legacy salvage into buckets
    legacy_neg = src.get("negotiation") if isinstance(src.get("negotiation"), dict) else {}
    if legacy_neg:
        if legacy_neg.get("price_mentioned"):
            offer = _to_bucket_item(
                str(legacy_neg.get("price_firm_text") or legacy_neg.get("price_value") or "oferta de precio"),
                confidence=0.7,
                turn_idx=turn_idx,
            )
            if offer:
                buckets.setdefault("offers", []).append(offer)
        if legacy_neg.get("concession_made"):
            c = _to_bucket_item(str(legacy_neg.get("concession_text") or "concesión"), confidence=0.65, turn_idx=turn_idx)
            if c:
                buckets.setdefault("concessions", []).append(c)
        if legacy_neg.get("deadline_claimed") or legacy_neg.get("urgency_claimed"):
            req = _to_bucket_item(str(legacy_neg.get("deadline_text") or legacy_neg.get("urgency_text") or "urgencia"), confidence=0.6, turn_idx=turn_idx)
            if req:
                buckets.setdefault("requests", []).append(req)

    legacy_claims = src.get("open_claims") if isinstance(src.get("open_claims"), list) else []
    for claim in legacy_claims:
        if not isinstance(claim, dict):
            continue
        item = _to_bucket_item(str(claim.get("evidence_text") or claim.get("value") or claim.get("label") or ""), confidence=float(claim.get("confidence", 0.5) or 0.5), turn_idx=int(claim.get("turn_idx") or turn_idx))
        if item:
            buckets.setdefault("claims", []).append(item)

    base["world_buckets"] = normalize_world_buckets(buckets, default_turn=turn_idx, max_items=8)

    meta = dict(base.get("world_state_meta") or {})
    raw_meta = src.get("world_state_meta") if isinstance(src.get("world_state_meta"), dict) else {}
    meta["turn_idx"] = int(raw_meta.get("turn_idx") or turn_idx or 0)
    meta["updated_fields"] = list(raw_meta.get("updated_fields") or [])[:40]
    meta["updated_buckets"] = list(raw_meta.get("updated_buckets") or [])[:20]
    meta["extractor_failed"] = bool(raw_meta.get("extractor_failed", False))
    meta["error"] = str(raw_meta.get("error", "") or "")[:200]
    unknown = raw_meta.get("unknown_claims", [])
    meta["unknown_claims"] = unknown if isinstance(unknown, list) else []
    base["world_state_meta"] = meta
    base["schema_version"] = "v3"
    return base


def migrate_belief_state_to_v3(belief_state: dict[str, Any] | None) -> dict[str, Any]:
    base = default_belief_state()
    src = dict(belief_state or {}) if isinstance(belief_state, dict) else {}

    buckets = dict(src.get("belief_buckets") or {}) if isinstance(src.get("belief_buckets"), dict) else {}
    if not buckets:
        # salvage from legacy hypotheses lists
        hyp = src.get("hypotheses") if isinstance(src.get("hypotheses"), list) else []
        if not hyp and isinstance(src.get("negotiation"), dict):
            hyp = src.get("negotiation", {}).get("hypotheses", [])
        items = []
        for item in hyp[:8]:
            if isinstance(item, str) and item.strip():
                items.append({"text": item[:180], "confidence": 0.55, "status": "active"})
        if items:
            buckets["hypotheses"] = items

    base["belief_buckets"] = normalize_belief_buckets(buckets)

    # planner signals salvage
    signals = dict(base.get("planner_signals") or {})
    uni = src.get("universal") if isinstance(src.get("universal"), dict) else {}
    dyn = uni.get("dynamics") if isinstance(uni.get("dynamics"), dict) else {}
    guide = uni.get("behavior_guidance") if isinstance(uni.get("behavior_guidance"), dict) else {}
    if isinstance(src.get("planner_signals"), dict):
        signals.update(src.get("planner_signals") or {})
    if dyn:
        signals["interaction_health"] = str(dyn.get("interaction_health", signals["interaction_health"]))
    if guide:
        try:
            signals["conflict_risk"] = float(guide.get("conflict_risk", signals["conflict_risk"]))
        except Exception:
            pass
        signals["recommended_move"] = str(guide.get("recommended_move", signals["recommended_move"]))
    signals["recovery_mode"] = bool(signals.get("recovery_mode", False))
    base["planner_signals"] = signals
    base["schema_version"] = "v3"
    return base


def migrate_state_to_v3_payload(world_state: dict[str, Any] | None, belief_state: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    return migrate_world_state_to_v3(world_state), migrate_belief_state_to_v3(belief_state)
