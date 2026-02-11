from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_policy_state, default_progress_state
from negotiation.schemas import default_policy_decision, default_world_state
from state import SessionState


def test_executor_receives_intent_hint(monkeypatch):
    captured = {}

    def fake_plan_phase_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "info_extract_critical"
        decision["micro_goal"] = "Pedir información clave."
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

    def fake_execute(messages):
        captured["messages"] = messages
        return "ok"

    deps = AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )

    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )

    state = SessionState(user_id="u", session_id="s")
    progress = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update(
        {
            "status": "active",
            "policy_id": "test_credibility",
            "step_idx": 0,
            "step_attempts": 0,
            "planner_request": "continue_policy",
            "slots_required": ["negotiation.other_buyer_text", "negotiation.evidence_offered"],
        }
    )
    progress["policy_state"] = policy_state
    state.progress_state = progress
    state.world_state = default_world_state()

    run_negotiation_agent(state, "hola", deps=deps)

    system_message = captured["messages"][0].content
    user_message = captured["messages"][1].content
    assert "universal message renderer" in system_message
    assert "policy_next_hint" in user_message
    assert "intent_next_hint" in user_message
    assert "policy_id" in user_message
    assert "STRATEGY SUMMARY" in user_message


def test_executor_prompt_contract_no_step_name_no_step_colon(monkeypatch):
    captured = {}

    def fake_plan_phase_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "info_extract_critical"
        decision["micro_goal"] = "Pedir información clave."
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

    def fake_execute(messages):
        captured["messages"] = messages
        return "ok"

    deps = AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )

    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )

    state = SessionState(user_id="u", session_id="s")
    progress = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update(
        {
            "status": "active",
            "policy_id": "test_credibility",
            "step_idx": 0,
            "step_attempts": 0,
            "planner_request": "continue_policy",
            "slots_required": ["negotiation.other_buyer_text", "negotiation.evidence_offered"],
        }
    )
    progress["policy_state"] = policy_state
    state.progress_state = progress
    state.world_state = default_world_state()

    run_negotiation_agent(state, "hola", deps=deps)

    user_message = captured["messages"][1].content
    assert "step_name" not in user_message
    assert "Step:" not in user_message


def test_executor_prompt_close_next_includes_fallback_rule(monkeypatch):
    captured = {}

    def fake_plan_phase_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "info_extract_critical"
        decision["micro_goal"] = "Pedir información clave."
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

    def fake_execute(messages):
        captured["messages"] = messages
        return "ok"

    deps = AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )

    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )

    state = SessionState(user_id="u", session_id="s")
    progress = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update(
        {
            "status": "active",
            "policy_id": "test_credibility",
            "step_idx": 0,
            "step_attempts": 0,
            "planner_request": "continue_policy",
            "slots_required": ["negotiation.other_buyer_text", "negotiation.evidence_offered"],
        }
    )
    progress["policy_state"] = policy_state
    state.progress_state = progress
    state.world_state = default_world_state()

    run_negotiation_agent(state, "hola", deps=deps)

    user_message = captured["messages"][1].content
    assert "CONSTRAINTS_STRUCT" in user_message
    assert "\"require_ask_if_missing\"" in user_message
