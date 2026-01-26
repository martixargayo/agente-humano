from negotiation.policy_planner import allowed_policy_ids
from negotiation.schemas import (
    default_belief_state,
    default_progress_state,
    default_world_state,
)


def test_guard_requires_price_not_mentioned_excludes_policy_when_price_mentioned():
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
