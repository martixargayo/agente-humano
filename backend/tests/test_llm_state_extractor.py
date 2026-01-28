import pytest

from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import (
    default_belief_state,
    default_intent_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from negotiation.world_state_updater import update_world_state
from state import SessionState


def test_update_world_state_applies_llm_patch(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "1")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "0")

    def fake_extract(_prev_world, _prev_belief, _user_message, _recent_history):
        return {
            "world_patch": {
                "price_mentioned": True,
                "price_value": 9000.0,
                "price_firm": True,
                "message_is_vague": False,
            },
            "belief_patch": {},
            "field_evidence": {
                "price_mentioned": {"evidence": "Precio 9.000€.", "confidence": 0.9},
                "price_value": {"evidence": "Precio 9.000€.", "confidence": 0.9},
                "price_firm": {"evidence": "Precio fijo.", "confidence": 0.8},
                "message_is_vague": {"evidence": "Mensaje directo.", "confidence": 0.7},
            },
            "decisions": {"should_update_beliefs": True, "message_is_vague": False},
            "reasons": ["price_signal"],
            "schema_version": "world_v1",
        }

    monkeypatch.setattr(
        "negotiation.world_state_updater.extract_state_patch_llm", fake_extract
    )

    world, meta = update_world_state(default_world_state(), "precio 9000")

    assert world["price_mentioned"] is True
    assert world["price_value"] == 9000.0
    assert world["price_firm"] is True
    assert world["message_is_vague"] is False
    assert meta["extractor_used"] is True
    assert meta["extractor_world_patch_keys"] == [
        "message_is_vague",
        "price_firm",
        "price_mentioned",
        "price_value",
    ]
    assert meta["extractor_confidence_summary"]["min"] == 0.7


def test_update_world_state_rejects_illegal_patch_key(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "1")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "0")

    def fake_extract(_prev_world, _prev_belief, _user_message, _recent_history):
        return {
            "world_patch": {"hacked": True},
            "belief_patch": {},
            "field_evidence": {"hacked": {"evidence": "nope", "confidence": 0.5}},
            "decisions": {"should_update_beliefs": False},
            "reasons": ["bad_key"],
            "schema_version": "world_v1",
        }

    monkeypatch.setattr(
        "negotiation.world_state_updater.extract_state_patch_llm", fake_extract
    )

    with pytest.raises(AssertionError, match="extractor_illegal_world_key"):
        update_world_state(default_world_state(), "precio 9000")


def test_validate_extractor_output_rejects_belief_patch_in_p0():
    from negotiation.llm_state_extractor import validate_extractor_output

    out = {
        "world_patch": {},
        "belief_patch": {"stance": {"deal_feasibility": 0.1}},
        "field_evidence": {},
        "decisions": {"should_update_beliefs": False},
        "reasons": ["x"],
        "schema_version": "world_v1",
    }
    with pytest.raises(AssertionError, match="extractor_belief_patch_not_allowed_p0"):
        validate_extractor_output(out)


def test_intent_replan_uses_llm_patch(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "1")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "0")
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index", lambda: None
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    def fake_extract(_prev_world, _prev_belief, _user_message, _recent_history):
        return {
            "world_patch": {
                "price_firm": True,
                "price_firm_text": "Precio firme.",
                "price_mentioned": True,
                "price_value": 9000.0,
            },
            "belief_patch": {},
            "field_evidence": {
                "price_firm": {"evidence": "Precio firme.", "confidence": 0.8},
                "price_mentioned": {"evidence": "Precio firme.", "confidence": 0.8},
                "price_value": {"evidence": "Precio firme.", "confidence": 0.8},
            },
            "decisions": {"should_update_beliefs": True},
            "reasons": ["firm_price"],
            "schema_version": "world_v1",
            "evidence_items": [
                {
                    "type": "FIRMNESS",
                    "text": "Precio firme.",
                    "value": None,
                    "source": "llm",
                    "confidence": 0.8,
                    "turn_idx": 1,
                    "raw": None,
                }
            ],
        }

    monkeypatch.setattr(
        "negotiation.world_state_updater.extract_state_patch_llm", fake_extract
    )

    def fake_plan_policy(*_args, **_kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "info_extract_critical"
        decision["micro_goal"] = "Pedir información clave."
        return decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*_args, **_kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def fake_execute(_messages):
        return "ok"

    deps = AgentDeps(
        plan_policy=fake_plan_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )

    state = SessionState(user_id="u3", session_id="s3")
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

    run_negotiation_agent(state, "precio 9000", deps=deps)

    trace = state.debug_trace[-1]
    intent_state = state.progress_state["intent_state"]
    assert trace["intent_transition"] == "replan"
    assert trace["planner_meta"]["intent_meta"]["replan_to"] == "closing"
    assert intent_state["intent_type"] == "closing"
