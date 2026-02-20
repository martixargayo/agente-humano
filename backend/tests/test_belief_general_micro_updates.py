from negotiation.belief_compat import update_belief_state
from negotiation.schemas import default_belief_state, default_world_state
from negotiation.world_state_updater import diff_world_state


def test_belief_allows_micro_negotiation_time_pressure_in_general_mode(monkeypatch):
    monkeypatch.setattr(
        "negotiation.belief_compat.extract_belief_patch_llm_v3",
        lambda **_kwargs: ({"metrics": {}, "dynamics": {}, "tom": {}, "reasons": {}}, {}, {}),
    )
    prev_world = default_world_state()
    world = default_world_state()
    world["negotiation"]["urgency_claimed"] = True
    world["negotiation"]["urgency_text"] = "lo antes posible"
    world["open_claims"] = [
        {
            "scope": "other_domain",
            "category": "risk",
            "label": "market_demand_uncertainty",
            "value": "x",
            "confidence": 0.8,
            "evidence_text": "me preocupa que nadie quiera comprarlo",
        }
    ]
    world_diff = diff_world_state(prev_world, world)
    prev_belief = default_belief_state()

    belief, _meta = update_belief_state(
        prev_belief_state=prev_belief,
        prev_world_state=prev_world,
        world_state=world,
        world_diff=world_diff,
        last_policy_executed=None,
        last_assistant_message="",
        user_message="me urge venderlo",
        context_snippet="",
        extractor_meta={},
        force_update=True,
        conversation_mode="general",
    )

    assert belief["negotiation"]["stance"]["time_pressure"] >= 0.65
