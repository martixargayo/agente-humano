import os

from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_policy_decision
from state import SessionState


def test_executed_policy_and_debug_trace_are_persisted(monkeypatch):
    os.environ.setdefault("OPENAI_API_KEY", "test")

    def fake_plan_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "hold_position"
        decision["reason"] = "x"
        decision["micro_goal"] = "y"
        decision["risk_posture"] = "mid"
        return decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*args, **kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def fake_execute(*args, **kwargs) -> str:
        return "ok-response"

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
    run_negotiation_agent(state, "hola", deps=deps)

    assert state.last_policy_executed is not None
    assert state.last_policy_executed.get("policy_id") == "hold_position"

    assert state.debug_trace
    trace = state.debug_trace[0]

    assert trace["executed_policy_raw"]["policy_id"] == "hold_position"
    assert trace["executed_policy_normalized"]["policy_id"] == "hold_position"
    assert trace["executed_policy_issues"] == []

    validation_issues = trace["validation_issues"]
    assert "world_in" in validation_issues
    assert "belief_in" in validation_issues
    assert "policy_out" in validation_issues
    assert "progress_out" in validation_issues

    assert state.last_policy_executed == trace["executed_policy_normalized"]


def test_executed_policy_can_differ_from_chosen_and_is_persisted(monkeypatch):
    os.environ.setdefault("OPENAI_API_KEY", "test")

    def fake_plan_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "hold_position"
        decision["reason"] = "chosen"
        decision["micro_goal"] = "chosen"
        decision["risk_posture"] = "mid"
        return decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*args, **kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def pre_execute_hook(state):
        # Simulamos que el executor decide ejecutar otra policy distinta
        executed = default_policy_decision()
        executed["policy_id"] = "deescalate_tension"
        executed["reason"] = "executed"
        executed["micro_goal"] = "executed"
        executed["risk_posture"] = "low"
        state["executed_policy"] = executed

    def fake_execute(*args, **kwargs) -> str:
        return "ok-response"

    deps = AgentDeps(
        plan_policy=fake_plan_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
        pre_execute_hook=pre_execute_hook,
    )

    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="u", session_id="s")
    run_negotiation_agent(state, "hola", deps=deps)

    # chosen != executed
    assert state.debug_trace
    trace = state.debug_trace[0]
    assert trace["policy_decision"]["policy_id"] == "hold_position"
    assert trace["executed_policy_normalized"]["policy_id"] == "deescalate_tension"

    # source-of-truth persistida
    assert state.last_policy_executed["policy_id"] == "deescalate_tension"
