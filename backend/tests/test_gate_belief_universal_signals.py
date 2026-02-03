from negotiation.gate_utils import gate_belief
from negotiation.schemas import default_world_state, default_belief_state


def test_gate_belief_opens_on_escalation_up():
    prev_world = default_world_state()
    world = default_world_state()
    world["interaction"]["escalation_signal"] = "up"
    skipped, _reason = gate_belief(
        world_diff={},
        prev_world=prev_world,
        world=world,
        prev_belief=default_belief_state(),
        turn_count=2,
        last_refresh_turn=1,
        interval=3,
    )
    assert skipped is False


def test_gate_belief_opens_on_universal_goal_change():
    prev_world = default_world_state()
    world = default_world_state()
    world["universal_state"]["goal"] = {"summary": "nuevo objetivo", "confidence": 0.6}
    skipped, _reason = gate_belief(
        world_diff={},
        prev_world=prev_world,
        world=world,
        prev_belief=default_belief_state(),
        turn_count=2,
        last_refresh_turn=1,
        interval=3,
    )
    assert skipped is False


def test_gate_belief_skips_when_no_delta_interval_hold():
    prev_world = default_world_state()
    world = default_world_state()
    skipped, reason = gate_belief(
        world_diff={},
        prev_world=prev_world,
        world=world,
        prev_belief=default_belief_state(),
        turn_count=2,
        last_refresh_turn=1,
        interval=3,
    )
    assert skipped is True
    assert reason == "no_delta_interval_hold"
