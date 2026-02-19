from negotiation.gate_utils import gate_belief
from negotiation.gating.fingerprints import world_buckets_fingerprint
from negotiation.schemas import default_belief_state, default_world_state


def test_gate_belief_opens_when_world_buckets_fingerprint_changes():
    prev_world = default_world_state()
    world = default_world_state()
    world["world_buckets"]["offers"] = [
        {
            "text": "Intercambio hoy por ITV",
            "confidence": 0.8,
            "raw_text": "si me pagas más hoy, yo te pago la ITV 2 años",
            "source_turn": 2,
        }
    ]
    skipped, reason = gate_belief(
        world_diff={},
        prev_world=prev_world,
        world=world,
        prev_belief=default_belief_state(),
        turn_count=2,
        last_refresh_turn=1,
        interval=3,
        prev_world_buckets_fingerprint=world_buckets_fingerprint(prev_world),
    )
    assert skipped is False
    assert reason == "world_buckets_changed"
