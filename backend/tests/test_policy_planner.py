from negotiation.policy_planner import allowed_policy_ids
from negotiation.policies import POLICIES, get_policy, policy_catalog_text
from negotiation.schemas import (
    default_belief_state,
    default_progress_state,
    default_world_state,
)


def test_allowed_policy_ids_filters_by_phase():
    world_state = default_world_state()
    belief_state = default_belief_state()
    progress_state = default_progress_state()
    progress_state["phase_state"]["phase"] = "opening"

    allowed = allowed_policy_ids(world_state, belief_state, progress_state)

    assert "close_with_conditions" not in allowed


def test_allowed_policy_ids_filters_by_required_inputs_true():
    world_state = default_world_state()
    belief_state = default_belief_state()
    progress_state = default_progress_state()

    allowed = allowed_policy_ids(world_state, belief_state, progress_state)
    assert "test_credibility" not in allowed

    world_state["negotiation"]["other_buyer_claimed"] = True
    allowed = allowed_policy_ids(world_state, belief_state, progress_state)
    assert "test_credibility" in allowed


def test_all_policies_define_phase_hints():
    for policy in POLICIES:
        assert policy.phase_hints, f"Policy {policy.policy_id} missing phase_hints"


def test_all_policies_define_new_contract_fields():
    for policy in POLICIES:
        assert isinstance(policy.required_inputs, list)
        for req in policy.required_inputs:
            assert isinstance(req, dict)
            assert "key" in req
            assert "op" in req
        assert isinstance(policy.target_slots, list)
        assert isinstance(policy.expected_effects, list)
        assert isinstance(policy.failure_modes, list)


def test_policy_catalog_includes_contract_fields():
    catalog = policy_catalog_text()
    assert "Required:" in catalog
    assert "Target slots:" in catalog
    assert "Expected:" in catalog
    assert "Failure:" in catalog


def test_delay_price_discussion_required_inputs_match_guard():
    policy = get_policy("delay_price_discussion")
    assert policy is not None
    assert "requires_price_not_mentioned" in (policy.guards or set())
    required_keys = {req.get("key") for req in policy.required_inputs}
    assert "price_mentioned" in required_keys
