from negotiation.policy_planner import allowed_policy_ids
from negotiation.policies import POLICIES, get_policy, policy_catalog_text
from negotiation.schemas import (
    default_belief_state,
    default_progress_state,
    default_world_state,
)


def test_guard_requires_price_not_mentioned_excludes_policy_when_price_mentioned():
    policy = get_policy("delay_price_discussion")
    assert policy is not None, "Spec requires delay_price_discussion policy to exist"
    assert "requires_price_not_mentioned" in (policy.guards or set())

    world_state = default_world_state()
    world_state["price_mentioned"] = True
    belief_state = default_belief_state()
    progress_state = default_progress_state()

    allowed = allowed_policy_ids(world_state, belief_state, progress_state)

    assert "delay_price_discussion" not in allowed


def test_required_guards_exclude_policies_without_safe_when_tense_when_tense():
    world_state = default_world_state()
    belief_state = default_belief_state()
    belief_state["dynamics"]["interaction_health"] = "tense"
    progress_state = default_progress_state()

    allowed = allowed_policy_ids(world_state, belief_state, progress_state)

    assert "challenge_anchor_indirect" not in allowed


def test_all_policies_define_phase_hints():
    for policy in POLICIES:
        assert policy.phase_hints, f"Policy {policy.policy_id} missing phase_hints"


def test_all_policies_define_new_contract_fields():
    for policy in POLICIES:
        assert isinstance(policy.required_inputs, list)
        assert isinstance(policy.target_slots, list)
        assert isinstance(policy.expected_effects, list)
        assert isinstance(policy.failure_modes, list)


def test_policy_catalog_includes_contract_fields():
    catalog = policy_catalog_text()
    assert "Required:" in catalog
    assert "Target slots:" in catalog
    assert "Expected:" in catalog
    assert "Failure:" in catalog
