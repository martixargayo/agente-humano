from negotiation.schemas import default_belief_state


def test_default_belief_state_has_v2_and_mirrors():
    belief = default_belief_state()
    assert "universal" in belief
    assert "negotiation" in belief
    assert "dynamics" in belief
    assert "tom" in belief
    metrics = belief["universal"]["metrics"]
    assert set(metrics.keys()) == {"trust", "cooperation", "clarity", "engagement"}
    dynamics = belief["universal"]["dynamics"]
    assert dynamics["interaction_health"] in {"stable", "tense", "stalled"}
    assert dynamics["escalation"] in {"up", "down", "none"}
    assert dynamics["commitment"] in {"hard", "soft", "none"}
