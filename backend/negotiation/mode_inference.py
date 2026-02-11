from __future__ import annotations


def compute_mode_score(world: dict) -> float:
    score = 0.0
    negotiation = world.get("negotiation", {}) if isinstance(world, dict) else {}
    if negotiation.get("price_mentioned"):
        score += 0.35
    if negotiation.get("deadline_claimed"):
        score += 0.20
    if negotiation.get("other_buyer_claimed"):
        score += 0.20
    if negotiation.get("min_price_claimed"):
        score += 0.25
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
