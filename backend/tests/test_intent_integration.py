from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import (
    default_belief_state,
    default_intent_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from state import SessionState


def _fake_deps(captured):
    def fake_plan_phase_policy(*args, **kwargs):
        decision = default_policy_decision()
        allowed = kwargs.get("allowed_policy_ids") or []
        decision["policy_id"] = allowed[0] if allowed else "info_extract_critical"
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

    return AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )


def _queue_world_states(monkeypatch, world_states):
    queue = list(world_states)

    def fake_update_world_state(_prev_world, _user_message, **_kwargs):
        if queue:
            return queue.pop(0), {"extractor_used": False}
        return default_world_state(), {"extractor_used": False}

    monkeypatch.setattr(
        "negotiation.negotiation_graph.update_world_state",
        fake_update_world_state,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )


def test_integration_info_extract_retarget_path(monkeypatch):
    captured = {}
    deps = _fake_deps(captured)
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    world_turn1 = default_world_state()
    world_turn1["message_is_vague"] = True
    world_turn2 = default_world_state()
    world_turn2.update(
        {
            "batna_claimed": True,
            "batna_text": "Otra oferta",
            "price_mentioned": True,
        }
    )
    world_turn3 = default_world_state()
    world_turn3.update(
        {
            "batna_claimed": True,
            "batna_text": "Otra oferta",
            "urgency_claimed": True,
            "urgency_text": "Necesito vender ya",
            "price_mentioned": True,
        }
    )

    _queue_world_states(monkeypatch, [world_turn1, world_turn2, world_turn3])

    state = SessionState(user_id="u", session_id="s")
    state.world_state = default_world_state()
    state.belief_state = default_belief_state()
    state.progress_state = default_progress_state()

    run_negotiation_agent(state, "no sé", deps=deps)
    trace1 = state.debug_trace[-1]
    assert state.progress_state["intent_state"]["status"] == "active"
    assert trace1["intent_transition"] in {"none", "advance", "retarget", "pivot", "continue"}

    run_negotiation_agent(state, "tengo otra oferta", deps=deps)
    trace2 = state.debug_trace[-1]
    intent_state2 = state.progress_state["intent_state"]
    assert trace2["intent_transition"] == "retarget"
    assert trace2["planner_meta"]["intent_meta"]["retarget_slot"] == "seller_urgency_reason"
    assert intent_state2["step_idx"] == 0
    assert intent_state2["step_attempts"] == 0
    assert intent_state2["steps"][0]["target_slot"] == "seller_urgency_reason"

    run_negotiation_agent(state, "me urge vender", deps=deps)
    trace3 = state.debug_trace[-1]
    intent_state3 = state.progress_state["intent_state"]
    assert trace3["intent_transition"] in {"succeed", "abandon"}
    assert intent_state3["status"] in {"succeeded", "abandoned"}


def test_integration_replan_to_closing(monkeypatch):
    captured = {}
    deps = _fake_deps(captured)
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    world_turn = default_world_state()
    world_turn.update(
        {
            "price_firm_text": "Precio firme",
            "price_mentioned": True,
            "price_value": 9500,
            "evidence_items": [
                {
                    "type": "FIRMNESS",
                    "text": "Precio firme",
                    "value": None,
                    "source": "regex",
                    "confidence": 0.8,
                    "turn_idx": 1,
                    "raw": None,
                }
            ],
        }
    )
    _queue_world_states(monkeypatch, [world_turn])

    state = SessionState(user_id="u2", session_id="s2")
    state.world_state = default_world_state()
    state.belief_state = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "step_attempts": 0,
            "slots": {
                "slots_required": ["seller_batna", "seller_urgency_reason"],
                "slots_optional": [],
                "slots_filled": {},
            },
        }
    )
    progress["intent_state"] = intent
    state.progress_state = progress

    run_negotiation_agent(state, "precio firme", deps=deps)
    trace = state.debug_trace[-1]
    intent_state = state.progress_state["intent_state"]
    assert trace["intent_transition"] == "replan"
    assert trace["planner_meta"]["intent_meta"]["replan_to"] == "closing"
    assert intent_state["intent_type"] == "closing"
    assert intent_state["status"] == "active"
