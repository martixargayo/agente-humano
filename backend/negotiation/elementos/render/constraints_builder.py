from __future__ import annotations

from typing import Dict

from ...policies import get_policy


def build_constraints_struct(
    world: dict,
    belief: dict,
    progress: dict,
    decision: dict,
    persona: dict,
    scene: dict,
    style: dict,
) -> Dict[str, object]:
    out: Dict[str, object] = {
        "forbid_claims": ["access_internal_systems", "physical_actions_done"],
        "forbid_formats": [],
        "disallow_numbers": False,
        "require_ask_if_missing": [],
        "max_questions": int(style.get("max_questions", 2)),
    }

    if not bool(style.get("markdown_allowed", False)):
        out["forbid_formats"].append("markdown")

    universal = (belief.get("universal") or {}) if isinstance(belief, dict) else {}
    dynamics = universal.get("dynamics", {}) if isinstance(universal.get("dynamics"), dict) else {}
    guidance = universal.get("behavior_guidance", {}) if isinstance(universal.get("behavior_guidance"), dict) else {}
    verification_need = float(guidance.get("verification_need", 0.0) or 0.0)
    conflict_risk = float(guidance.get("conflict_risk", 0.0) or 0.0)
    epistemic_style = str(guidance.get("epistemic_style", "neutral") or "neutral")

    if dynamics.get("interaction_health") in ("tense", "stalled") or conflict_risk >= 0.6:
        out["max_questions"] = 1
    elif verification_need >= 0.6:
        out["max_questions"] = min(int(style.get("max_questions", 2)), max(2, int(out.get("max_questions", 2))))

    out["epistemic_style"] = epistemic_style if epistemic_style in {"hedged", "neutral", "direct"} else "neutral"
    out["must_hedge"] = out["epistemic_style"] == "hedged" or verification_need >= 0.6
    out["verify_first"] = verification_need >= 0.6

    policy_id = decision.get("policy_id") or ""
    policy = get_policy(policy_id)
    guards = set(policy.guards or []) if policy else set()
    if "avoid_mentioning_own_numbers" in guards:
        out["disallow_numbers"] = True

    if progress.get("conversation_mode") == "negotiation":
        negotiation = world.get("negotiation", {}) if isinstance(world, dict) else {}
        if not negotiation.get("price_mentioned"):
            out["require_ask_if_missing"].append("price")

    out["forbid_formats"] = sorted(set(out["forbid_formats"]))
    out["forbid_claims"] = sorted(set(out["forbid_claims"]))
    out["require_ask_if_missing"] = list(dict.fromkeys(out["require_ask_if_missing"]))[:6]
    return out
