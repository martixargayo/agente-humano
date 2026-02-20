from negotiation.phase_state_updater import _gate_effective_phase
from negotiation.perception.clarity_signals import compute_clarity_signals


def test_compute_clarity_signals_vague_when_no_world_bucket_signals():
    world = {"world_buckets": {"offers": [], "claims": [], "requests": [], "constraints": [], "interests": [], "concessions": []}}
    out = compute_clarity_signals(world)
    assert out["clarity_vague"] is True
    assert out["signal_count"] == 0


def test_phase_gate_no_nameerror_and_holds_climate_when_vague():
    world = {"world_buckets": {"offers": [], "claims": [], "requests": [], "constraints": [], "interests": [], "concessions": []}}
    belief = {"planner_signals": {}}
    phase = _gate_effective_phase("climate", world, belief, turn_count=1, recovery_mode=False)
    assert phase == "climate"


def test_phase_gate_advances_when_non_vague():
    world = {"world_buckets": {"offers": [], "claims": [{"text": "x", "raw_text": "x", "confidence": 0.7, "source_turn": 1}], "requests": [], "constraints": [], "interests": [], "concessions": []}}
    belief = {"planner_signals": {}}
    phase = _gate_effective_phase("climate", world, belief, turn_count=1, recovery_mode=False)
    assert phase == "interests"
