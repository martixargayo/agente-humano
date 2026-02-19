from negotiation.gating.fingerprints import world_buckets_fingerprint
from negotiation.nodes.belief_node import belief_updater_node
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state


def test_belief_node_refreshes_when_world_buckets_fingerprint_changes():
    called = {"n": 0}

    def _fake_update_belief_state(**_kwargs):
        called["n"] += 1
        return default_belief_state(), {"belief_update_failed": False, "belief_update_skipped": False}

    prev_world = default_world_state()
    curr_world = default_world_state()
    curr_world["world_buckets"]["concessions"] = [
        {
            "text": "Ofrece papeleo gratis por más dinero hoy.",
            "confidence": 0.8,
            "raw_text": "si me pagas más hoy, te hago el papeleo gratis",
            "source_turn": 2,
        }
    ]
    progress = default_progress_state()
    progress["gate_state"]["last_belief_refresh_turn"] = 1
    progress["gate_state"]["world_buckets_fingerprint_prev"] = world_buckets_fingerprint(prev_world)

    state = {
        "deps": type("Deps", (), {"update_belief_state": staticmethod(_fake_update_belief_state)})(),
        "belief_state": default_belief_state(),
        "prev_world_state": prev_world,
        "world_state": curr_world,
        "world_diff": {},
        "progress_state": progress,
        "turn_count": 2,
        "conversation_mode": "general",
        "extractor_meta": {},
        "last_policy_executed": None,
        "last_assistant_message": "",
        "user_message": "si me pagas más hoy, te hago el papeleo gratis",
        "recent_history_text": "",
    }

    out = belief_updater_node(state)
    assert called["n"] == 1
    assert out["belief_update_meta"].get("belief_update_skipped") is False
