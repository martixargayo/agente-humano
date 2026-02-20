from __future__ import annotations


def compute_mode_score(world: dict) -> float:
    score = 0.0
    buckets = world.get("world_buckets", {}) if isinstance(world, dict) else {}
    offers = buckets.get("offers", []) if isinstance(buckets, dict) else []
    constraints = buckets.get("constraints", []) if isinstance(buckets, dict) else []
    requests = buckets.get("requests", []) if isinstance(buckets, dict) else []
    if isinstance(offers, list) and offers:
        score += 0.35
    if isinstance(requests, list) and requests:
        score += 0.20
    if isinstance(constraints, list) and constraints:
        score += 0.45
    return min(score, 1.0)


def update_conversation_mode(progress: dict, world: dict, turn_idx: int) -> dict:
    current = progress.get("conversation_mode", "general") or "general"
    confidence = float(progress.get("mode_confidence", 0.0) or 0.0)
    score = compute_mode_score(world or {})

    confidence = confidence * 0.7 + score * 0.3

    last_switch = int(progress.get("mode_last_switch_turn", 0) or 0)
    if current == "general" and confidence >= 0.70:
        current = "negotiation"
        last_switch = turn_idx
    elif current == "negotiation" and confidence <= 0.30 and (turn_idx - last_switch) >= 2:
        current = "general"
        last_switch = turn_idx

    progress["conversation_mode"] = current
    progress["mode_confidence"] = max(0.0, min(1.0, confidence))
    progress["mode_last_switch_turn"] = last_switch
    return progress
