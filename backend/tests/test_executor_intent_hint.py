from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_intent_state, default_progress_state
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
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
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
    assert "Paso actual" in system_message
    assert "Slot objetivo" in system_message
    assert "Policy target slots" in system_message
    assert "Expected effects" in system_message
    assert "Step:" not in system_message


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
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
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
    assert "step_name" not in system_message
    assert "Step:" not in system_message


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
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )

    state = SessionState(user_id="u", session_id="s")
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Cerrar siguiente paso",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "close_next",
                    "target_slot": "",
                    "success_if_filled": [],
                }
            ],
            "step_idx": 0,
            "slots": {"slots_required": [], "slots_optional": [], "slots_filled": {}},
        }
    )
    progress["intent_state"] = intent
    state.progress_state = progress
    state.world_state = default_world_state()

    run_negotiation_agent(state, "hola", deps=deps)

    system_message = captured["messages"][0].content
    assert "está vacío" in system_message
