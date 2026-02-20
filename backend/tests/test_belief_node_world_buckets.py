from negotiation.nodes.belief_node import belief_updater_node
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state


def test_belief_node_invokes_extractor_when_world_buckets_change(monkeypatch):
    prev_world = default_world_state()
    world = default_world_state()
    world["world_buckets"]["offers"] = [{"text": "oferta", "confidence": 0.8, "source_turn": 2}]

    captured = {"called": False}

    def _fake_extract(**kwargs):
        captured["called"] = True
        belief = default_belief_state()
        belief["belief_buckets"]["hypotheses"] = [{"text": "h", "confidence": 0.7, "status": "active"}]
        return belief, {"belief_latency_ms": 1}

    monkeypatch.setattr("negotiation.nodes.belief_node.extract_belief_state_llm_v1", _fake_extract)

    state = {
        "deps": object(),
        "world_diff": {"world_buckets": {"offers": ["changed"]}},
        "prev_world_state": prev_world,
        "world_state": world,
        "belief_state": default_belief_state(),
        "progress_state": default_progress_state(),
        "turn_count": 2,
        "user_message": "hola",
    }

    out = belief_updater_node(state)

    assert captured["called"] is True
    assert out["belief_update_meta"]["belief_update_skipped"] is False
