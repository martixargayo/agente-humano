import os

from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_policy_decision, default_world_state
from state import SessionState


def test_executed_policy_and_debug_trace_are_persisted(monkeypatch):
    os.environ.setdefault("OPENAI_API_KEY", "test")

    def fake_plan_phase_policy(*args, **kwargs):
        decision = default_policy_decision()
        allowed = kwargs.get("allowed_policy_ids") or []
        decision["policy_id"] = allowed[0] if allowed else "rapport_build"
        decision["reason"] = "x"
        decision["micro_goal"] = "y"
        decision["risk_posture"] = "mid"
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*args, **kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def fake_execute(*args, **kwargs) -> str:
        return "ok-response"

    deps = AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )

    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="u", session_id="s")
    world_state = default_world_state()
    world_state["price_mentioned"] = True
    state.world_state = world_state
    run_negotiation_agent(state, "hola", deps=deps)

    assert state.last_policy_executed is not None
    assert state.debug_trace
    trace = state.debug_trace[0]
    assert state.last_policy_executed.get("policy_id") == trace["policy_decision"]["policy_id"]

    assert trace["executed_policy_raw"]["policy_id"] == trace["policy_decision"]["policy_id"]
    assert trace["executed_policy_normalized"]["policy_id"] == trace["policy_decision"]["policy_id"]
    assert trace["executed_policy_issues"] == []

    validation_issues = trace["validation_issues"]
    assert "world_in" in validation_issues
    assert "belief_in" in validation_issues
    assert "policy_out" in validation_issues
    assert "progress_out" in validation_issues

    assert state.last_policy_executed == trace["executed_policy_normalized"]


def test_executed_policy_can_differ_from_chosen_and_is_persisted(monkeypatch):
    os.environ.setdefault("OPENAI_API_KEY", "test")

    def fake_plan_phase_policy(*args, **kwargs):
        decision = default_policy_decision()
        allowed = kwargs.get("allowed_policy_ids") or []
        decision["policy_id"] = allowed[0] if allowed else "rapport_build"
        decision["reason"] = "chosen"
        decision["micro_goal"] = "chosen"
        decision["risk_posture"] = "mid"
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*args, **kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def fake_validate_and_repair(
        response_text, constraints_struct, policy_decision, world_state, **_kwargs
    ):
        meta = {
            "violations": ["mock"],
            "repaired_used": True,
            "model": "mock",
            "override_policy_id": "deescalate_tension",
            "override_reason": "mock_override",
        }
        return response_text, ["mock"], meta

    def fake_execute(*args, **kwargs) -> str:
        return "ok-response"

    deps = AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )

    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.nodes.executor_node.validate_and_repair",
        fake_validate_and_repair,
    )

    state = SessionState(user_id="u", session_id="s")
    world_state = default_world_state()
    world_state["price_mentioned"] = True
    state.world_state = world_state
    run_negotiation_agent(state, "hola", deps=deps)

    # chosen != executed
    assert state.debug_trace
    trace = state.debug_trace[0]
    assert trace["policy_decision"]["policy_id"]
    assert trace["executed_policy_normalized"]["policy_id"] == "deescalate_tension"
    assert trace["override_policy_id"] == "deescalate_tension"
    assert trace["override_reason"] == "mock_override"

    # source-of-truth persistida
    assert state.last_policy_executed["policy_id"] == "deescalate_tension"
