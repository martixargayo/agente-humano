import os

from negotiation.belief_governor import derive_behavior_guidance
from negotiation.policy_planner import allowed_policy_ids
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state


def test_belief_governor_prefers_probe_with_high_risk_signals():
    belief = default_belief_state()
    belief["universal"]["dynamics"]["interaction_health"] = "tense"
    belief["universal"]["reasons"] = {"evasion_signal": {"weight": 1, "confidence": 1, "evidence": "evade"}}
    belief["negotiation"]["stance"] = {"risk_level": 1.0}
    world = default_world_state()
    world["negotiation_v2"]["evidence"] = []
    guidance, _ = derive_behavior_guidance(belief, world)
    assert guidance["verification_need"] >= 0.6
    assert guidance["epistemic_style"] == "hedged"


def test_required_beliefs_filter_is_flagged(monkeypatch):
    world = default_world_state()
    belief = default_belief_state()
    belief["universal"]["behavior_guidance"]["verification_need"] = 0.0
    progress = default_progress_state()

    monkeypatch.setenv("POLICY_REQUIRED_BELIEFS_ENABLED", "0")
    no_flag = allowed_policy_ids(world, belief, progress, {})

    monkeypatch.setenv("POLICY_REQUIRED_BELIEFS_ENABLED", "1")
    with_flag = allowed_policy_ids(world, belief, progress, {})

    assert "deescalate_tension" in no_flag
    assert "deescalate_tension" not in with_flag
