from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import (
    default_belief_state,
    default_policy_decision,
    default_world_state,
)
from state import SessionState


def _smoke_deps():
    def fake_plan_phase_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "rapport_build"
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.9,
            "reasons": ["smoke"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, decision, {"planner_meta": {"smoke": True}}

    def fake_update_belief_state(*args, **kwargs):
        return default_belief_state(), {"belief_meta": {"smoke": True}}

    def fake_execute(messages):
        return "Perfecto, avancemos con números concretos."

    def fake_summarize(existing_summary, new_block):
        return (existing_summary + "\n" + new_block).strip()

    return AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
        summarize=fake_summarize,
    )


def test_negotiation_pipeline_two_turns_smoke(monkeypatch):
    deps = _smoke_deps()

    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.update_world_state",
        lambda _prev_world, _user_message, **_kwargs: (default_world_state(), {"extractor_used": False}),
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )

    state = SessionState(user_id="smoke", session_id="pipeline")
    reply_1, state = run_negotiation_agent(state, "¿Cuál es tu mejor precio?", deps=deps)
    reply_2, state = run_negotiation_agent(state, "Podría cerrar hoy si mejoras algo.", deps=deps)

    assert "avancemos" in reply_1
    assert "avancemos" in reply_2
    assert state.turn_count == 4
    assert len(state.debug_trace) == 2
    assert state.last_policy_executed["policy_id"] == "rapport_build"


def test_max_total_cost_margin_flag_smoke(monkeypatch):
    deps = _smoke_deps()

    monkeypatch.setenv("MAX_TOTAL_COST_MARGIN", "0.15")
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.update_world_state",
        lambda _prev_world, _user_message, **_kwargs: (default_world_state(), {"extractor_used": False}),
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )

    state = SessionState(user_id="smoke", session_id="margin")
    run_negotiation_agent(state, "¿Lo dejas en 9800?", deps=deps)

    assert state.debug_trace[-1]["max_total_cost_margin"] == 0.15
