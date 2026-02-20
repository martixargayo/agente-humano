# backend/negotiation/belief_state_updater.py
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from .schemas import BeliefState, WorldState, default_belief_state
from .validation import normalize_belief_buckets

logger = logging.getLogger(__name__)


def _belief_fingerprint(state: dict) -> str:
    payload = json.dumps(state or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def merge_belief_buckets_update_not_rewrite(prev: dict, patch: dict) -> dict:
    limits = {"hypotheses": 6, "strategy_notes": 3, "risk_flags": 3, "watch_items": 3}
    out = {k: list(v) for k, v in normalize_belief_buckets(prev).items()}
    incoming = normalize_belief_buckets(patch)

    def _key(text: str) -> str:
        return str(text or "").strip().lower()

    for bucket, max_items in limits.items():
        index = {_key(it.get("text", "")): dict(it) for it in out.get(bucket, []) if isinstance(it, dict)}
        for item in incoming.get(bucket, []):
            key = _key(item.get("text", ""))
            if not key:
                continue
            prev_item = index.get(key)
            if prev_item is None or float(item.get("confidence", 0.0)) >= float(prev_item.get("confidence", 0.0)):
                index[key] = dict(item)
        vals = sorted(index.values(), key=lambda d: float(d.get("confidence", 0.0)), reverse=True)[:max_items]
        out[bucket] = vals
    return out


def _derive_planner_signals(world_state: dict, belief_buckets: dict, progress_loop_flags: list[str] | None = None) -> dict[str, Any]:
    claims = list((world_state.get("world_buckets") or {}).get("claims", []) or [])
    constraints = list((world_state.get("world_buckets") or {}).get("constraints", []) or [])
    risks = list((belief_buckets or {}).get("risk_flags", []) or [])
    looping = bool(progress_loop_flags)

    conflict_risk = 0.0
    if risks:
        conflict_risk = max(conflict_risk, 0.6)
    if len(claims) > 3 or len(constraints) > 3:
        conflict_risk = max(conflict_risk, 0.4)
    if looping:
        conflict_risk = max(conflict_risk, 0.7)

    interaction_health = "stable"
    if conflict_risk >= 0.7:
        interaction_health = "stalled"
    elif conflict_risk >= 0.5:
        interaction_health = "tense"

    recommended_move = "hold"
    if conflict_risk >= 0.7:
        recommended_move = "deescalate"
    elif len(constraints) > 0:
        recommended_move = "tradeoff"

    return {
        "interaction_health": interaction_health,
        "conflict_risk": round(float(conflict_risk), 3),
        "recommended_move": recommended_move,
        "recovery_mode": bool(interaction_health in {"tense", "stalled"} or looping),
    }


def update_belief_state(
    prev_belief_state: BeliefState | None,
    prev_world_state: WorldState,
    world_state: WorldState,
    world_diff: dict,
    last_policy_executed: dict | None = None,
    last_assistant_message: str = "",
    user_message: str = "",
    context_snippet: str = "",
    extractor_meta: dict | None = None,
    force_update: bool = True,
    conversation_mode: str = "general",
) -> tuple[BeliefState, dict]:
    del prev_world_state, world_diff, last_policy_executed, last_assistant_message, user_message, context_snippet, extractor_meta, force_update, conversation_mode

    started = time.perf_counter()
    previous = dict(prev_belief_state or default_belief_state())
    prev_buckets = (previous or {}).get("belief_buckets", {}) if isinstance(previous, dict) else {}

    # Minimal LLM-first model: belief buckets are updated from world bucket signals only.
    world_buckets = dict((world_state or {}).get("world_buckets") or {})
    patch: dict[str, list[dict]] = {"hypotheses": [], "strategy_notes": [], "risk_flags": [], "watch_items": []}

    for offer in (world_buckets.get("offers") or [])[:2]:
        if isinstance(offer, dict):
            text = str(offer.get("text") or "oferta detectada").strip()
            if text:
                patch["hypotheses"].append({"text": f"La otra parte mantiene: {text[:120]}", "confidence": float(offer.get("confidence", 0.55) or 0.55), "status": "active"})
    for cons in (world_buckets.get("constraints") or [])[:2]:
        if isinstance(cons, dict):
            text = str(cons.get("text") or "restricción detectada").strip()
            if text:
                patch["risk_flags"].append({"text": text[:120], "confidence": float(cons.get("confidence", 0.6) or 0.6), "status": "active"})
    for req in (world_buckets.get("requests") or [])[:2]:
        if isinstance(req, dict):
            text = str(req.get("text") or "petición detectada").strip()
            if text:
                patch["strategy_notes"].append({"text": f"Responder a petición: {text[:100]}", "confidence": 0.55, "status": "active"})

    normalized_patch = normalize_belief_buckets(patch)
    merged_buckets = merge_belief_buckets_update_not_rewrite(prev_buckets, normalized_patch)
    planner_signals = _derive_planner_signals(world_state, merged_buckets)

    belief_state: BeliefState = {
        "schema_version": "v3",
        "belief_buckets": merged_buckets,
        "planner_signals": planner_signals,
    }

    before_fp = _belief_fingerprint(previous)
    after_fp = _belief_fingerprint(belief_state)

    meta = {
        "belief_update_failed": False,
        "belief_update_error": "",
        "belief_update_skipped": False,
        "belief_merge_changed": before_fp != after_fp,
        "belief_updated_fields": sorted(list(belief_state.keys())),
        "belief_latency_ms": int((time.perf_counter() - started) * 1000),
        "belief_noop_reason": "" if before_fp != after_fp else "merge_no_effect",
        "belief_gate_skip_reason": "",
        "belief_node_entered": True,
        "belief_updater_invoked": True,
    }
    return belief_state, meta
