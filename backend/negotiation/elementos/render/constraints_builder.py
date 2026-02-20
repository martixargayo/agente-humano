from __future__ import annotations

from typing import Dict

from ...policies import get_policy
from .carlos_buyer_preset import get_carlos_constraints_struct, is_carlos_buyer_render_ids


def build_constraints_struct(
    world: dict,
    belief: dict,
    progress: dict,
    decision: dict,
    persona: dict,
    scene: dict,
    style: dict,
) -> Dict[str, object]:
    if is_carlos_buyer_render_ids(
        persona.get("persona_id"),
        scene.get("scene_id"),
        style.get("style_id"),
    ):
        return get_carlos_constraints_struct()

    out: Dict[str, object] = {
        "forbid_claims": ["access_internal_systems", "physical_actions_done"],
        "forbid_formats": [],
        "disallow_numbers": False,
        "require_ask_if_missing": [],
        "max_questions": int(style.get("max_questions", 2)),
    }

    if not bool(style.get("markdown_allowed", False)):
        out["forbid_formats"].append("markdown")

    planner = (belief.get("planner_signals") or {}) if isinstance(belief, dict) else {}
    interaction_health = str(planner.get("interaction_health", "stable") or "stable")
    conflict_risk = float(planner.get("conflict_risk", 0.0) or 0.0)
    verification_need = 0.0
    epistemic_style = "neutral"

    if interaction_health in ("tense", "stalled") or conflict_risk >= 0.6:
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
        world_meta = world.get("world_state_meta", {}) if isinstance(world, dict) else {}
        if not bool(world_meta.get("price_mentioned", False)):
            out["require_ask_if_missing"].append("price")

    out["forbid_formats"] = sorted(set(out["forbid_formats"]))
    out["forbid_claims"] = sorted(set(out["forbid_claims"]))
    out["require_ask_if_missing"] = list(dict.fromkeys(out["require_ask_if_missing"]))[:6]
    return out
