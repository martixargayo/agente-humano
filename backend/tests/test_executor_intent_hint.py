from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_intent_state, default_progress_state
from negotiation.schemas import default_policy_decision, default_world_state
from state import SessionState


def test_executor_receives_intent_hint(monkeypatch):
    captured = {}

    def fake_plan_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "info_extract_critical"
        decision["micro_goal"] = "Pedir información clave."
        return decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*args, **kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def fake_execute(messages):
        captured["messages"] = messages
        return "ok"

    deps = AgentDeps(
        plan_policy=fake_plan_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )

    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="u", session_id="s")
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Aclarar términos",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "slots": {"slots_required": ["price"], "slots_optional": [], "slots_filled": {}},
        }
    )
    progress["intent_state"] = intent
    state.progress_state = progress
    state.world_state = default_world_state()

    run_negotiation_agent(state, "hola", deps=deps)

    system_message = captured["messages"][0].content
    assert "Intención activa" in system_message
    assert "Step" in system_message
    assert "Slot objetivo" in system_message
    assert "step_name" not in system_message
