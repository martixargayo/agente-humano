from negotiation.intent_manager import update_intent_state
from negotiation.precedence import compute_precedence
from negotiation.schemas import (
    default_belief_state,
    default_intent_state,
    default_progress_state,
    default_world_state,
)
def test_compute_precedence_recovery_guard_overrides_signals():
    world = default_world_state()
    world["price_firm"] = True
    belief = default_belief_state()
    belief["dynamics"]["interaction_health"] = "tense"

    prec = compute_precedence(world=world, belief=belief, intent=None)

    assert prec.mode == "recovery_guard"
    assert prec.phase_floor == "recovery"
    assert prec.allow_closing is False


def test_compute_precedence_discovery_on_claims():
    world = default_world_state()
    world["other_buyer_claimed"] = True

    prec = compute_precedence(world=world, belief=default_belief_state(), intent=None)

    assert prec.mode == "discovery"
    assert "credibility_check" in prec.min_policy_tags


def test_compute_precedence_price_firm_without_requirements():
    world = default_world_state()
    world["price_firm"] = True

    prec = compute_precedence(world=world, belief=default_belief_state(), intent=None)

    assert prec.mode == "bargaining"
    assert prec.allow_closing is False


def test_compute_precedence_price_firm_with_concession():
    world = default_world_state()
    world["price_firm"] = True
    world["concession_made"] = True

    prec = compute_precedence(world=world, belief=default_belief_state(), intent=None)

    assert prec.mode == "closing_push"
    assert prec.phase_floor == "closing"
    assert prec.allow_closing is True


def test_compute_precedence_concession_bargaining():
    world = default_world_state()
    world["price_mentioned"] = True
    world["concession_made"] = True

    prec = compute_precedence(world=world, belief=default_belief_state(), intent=None)

    assert prec.mode == "bargaining"

def test_intent_pauses_under_recovery_guard():
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_type": "closing",
            "steps": [
                {"kind": "close_next", "target_slot": "", "success_if_filled": []},
            ],
        }
    )
    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        user_message="",
        turn_count=2,
        precedence={"mode": "recovery_guard"},
    )

    assert updated["status"] == "paused"
    assert meta["intent_transition"] == "pause"
