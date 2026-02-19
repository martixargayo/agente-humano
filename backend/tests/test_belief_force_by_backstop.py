from negotiation.nodes.belief_node import belief_updater_node
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state


def test_belief_node_forces_refresh_when_backstop_reasons_present(monkeypatch):
    called = {"n": 0}

    def _fake_update_belief_state(**_kwargs):
        called["n"] += 1
        return default_belief_state(), {"belief_update_failed": False, "belief_update_skipped": False}

    state = {
        "deps": type("Deps", (), {"update_belief_state": staticmethod(_fake_update_belief_state)})(),
        "belief_state": default_belief_state(),
        "prev_world_state": default_world_state(),
        "world_state": default_world_state(),
        "world_diff": {},
        "progress_state": default_progress_state(),
        "turn_count": 2,
        "conversation_mode": "general",
        "extractor_meta": {"backstop_reasons": ["urgency_financial_backstop"]},
        "last_policy_executed": None,
        "last_assistant_message": "",
        "user_message": "necesito dinero",
        "recent_history_text": "",
    }

    out = belief_updater_node(state)
    assert called["n"] == 1
    assert out["belief_update_meta"].get("forced_by_backstop") is True

