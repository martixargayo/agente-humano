import copy

import negotiation.legacy.intent_manager as intent_manager
from negotiation.legacy.intent_manager import build_steps, update_intent_state
from negotiation.schemas import (
    StepKind,
    default_belief_state,
    default_intent_state,
    default_progress_state,
    default_world_state,
)


META_KEYS = {
    "intent_transition",
    "retarget_slot",
    "replan_to",
    "pivot_reason",
    "pivot_strategy",
    "reasons",
    "success_reasons",
    "commitment_level",
}


def _active_intent_with_step(step_kind: str, target_slot: str) -> dict:
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": step_kind,
                    "target_slot": target_slot,
                    "success_if_filled": [target_slot] if target_slot else [],
                }
            ],
            "step_idx": 0,
            "step_attempts": 0,
            "max_attempts_per_step": 1,
            "slots": {
                "slots_required": ["seller_batna", "seller_urgency_reason"],
                "slots_optional": [],
                "slots_filled": {},
            },
        }
    )
    return intent


def test_meta_contract_keys_always_present():
    intent, meta, _hint = update_intent_state(
        prev_intent=default_intent_state(),
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        user_message="no sé",
        turn_count=1,
    )
    assert META_KEYS.issubset(meta.keys())
    assert meta["reasons"] is not None
    assert meta["success_reasons"] is not None
    assert intent


def test_active_intent_hint_matches_current_step():
    intent = _active_intent_with_step("probe_open", "seller_batna")
    updated, _meta, hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        user_message="sigo pensando",
        turn_count=2,
    )
    step = updated["steps"][updated["step_idx"]]
    assert updated["status"] == "active"
    assert step["kind"] in StepKind.__args__
    assert step["target_slot"] != "unknown"
    assert hint["intent_active"] is True
    assert hint["step_kind"] == step["kind"]
    if step["kind"] == "close_next":
        assert hint["target_slot"] == step["target_slot"]
    else:
        assert hint["target_slot"] == step["target_slot"]


def test_build_steps_missing_empty_returns_close_next():
    steps = build_steps("info_extract", [])
    assert steps == [
        {
            "kind": "close_next",
            "target_slot": "",
            "success_if_filled": [],
        }
    ]


def test_hydration_legacy_string_steps_sets_steps_hydrated_and_valid_step():
    intent = _active_intent_with_step("probe_open", "seller_batna")
    intent["steps"] = ["legacy"]
    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        user_message="no sé",
        turn_count=3,
    )
    assert "steps_hydrated" in meta["reasons"]
    assert updated["steps"]
    assert updated["step_idx"] == 0
    assert updated["step_attempts"] == 0
    assert updated["steps"][0]["target_slot"] == "seller_batna"


def test_hydration_empty_steps_missing_empty_produces_close_next():
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Cerrar",
            "intent_type": "info_extract",
            "steps": [],
            "step_idx": 0,
            "step_attempts": 0,
            "slots": {"slots_required": [], "slots_optional": [], "slots_filled": {}},
        }
    )
    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        user_message="ok",
        turn_count=4,
    )
    assert "steps_hydrated" in meta["reasons"]
    assert updated["step_idx"] == 0
    assert updated["step_attempts"] == 0
    assert updated["steps"][0]["kind"] == "close_next"
    assert updated["steps"][0]["target_slot"] == ""


def test_retarget_guardrail_forces_step0_target_and_success_if_filled(monkeypatch):
    intent = _active_intent_with_step("probe_open", "seller_batna")
    intent["slots"]["slots_filled"] = {
        "seller_batna": {"value": "otra oferta", "evidence": "x", "confidence": 0.6, "source": "world_state"}
    }

    def fake_build_steps(_intent_type, _missing):
        return [
            {
                "kind": "probe_open",
                "target_slot": "wrong_slot",
                "success_if_filled": ["wrong_slot"],
            }
        ]

    monkeypatch.setattr(intent_manager, "build_steps", fake_build_steps)

    updated, meta, _hint = update_intent_state(
        prev_intent=copy.deepcopy(intent),
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        user_message="vale",
        turn_count=5,
    )
    assert meta["intent_transition"] == "retarget"
    assert meta["retarget_slot"] == "seller_urgency_reason"
    assert updated["step_idx"] == 0
    assert updated["step_attempts"] == 0
    assert updated["steps"][0]["target_slot"] == meta["retarget_slot"]
    assert updated["steps"][0]["success_if_filled"] == [meta["retarget_slot"]]


def test_replan_sets_transition_and_replan_to_closing():
    intent = _active_intent_with_step("probe_open", "seller_batna")
    intent["created_turn"] = 1
    world_state = default_world_state()
    world_state["negotiation"]["price_mentioned"] = True
    world_state["negotiation"]["price_value"] = 9200
    world_state["evidence_items"] = [
        {
            "type": "FIRMNESS",
            "text": "precio firme",
            "value": None,
            "source": "regex",
            "confidence": 0.8,
            "turn_idx": 1,
            "raw": None,
        }
    ]

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world_state,
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        user_message="precio firme",
        turn_count=6,
    )
    assert meta["intent_transition"] == "replan"
    assert meta["replan_to"] == "closing"
    assert updated["intent_type"] == "closing"
    assert updated["status"] == "active"
    assert updated["steps"]
    assert updated["step_idx"] == 0


def test_weak_firmness_does_not_replan():
    intent = _active_intent_with_step("probe_open", "seller_batna")
    world_state = default_world_state()
    world_state["negotiation"]["price_mentioned"] = True
    world_state["negotiation"]["price_value"] = 9200
    world_state["evidence_items"] = [
        {
            "type": "FIRMNESS",
            "text": "no negocio",
            "value": None,
            "source": "regex",
            "confidence": 0.45,
            "turn_idx": 1,
            "raw": None,
        }
    ]

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=world_state,
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        user_message="no negocio",
        turn_count=6,
    )
    assert meta["intent_transition"] != "replan"
    assert updated["intent_type"] != "closing"


def test_pivot_sets_reason_and_strategy_and_changes_kind():
    intent = _active_intent_with_step("request_evidence", "seller_batna")
    intent["step_attempts"] = 0
    intent["max_attempts_per_step"] = 1
    intent["created_turn"] = 7

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        user_message="vale",
        turn_count=7,
    )
    assert meta["intent_transition"] == "pivot"
    assert meta["pivot_reason"]
    assert meta["pivot_strategy"]
    assert updated["steps"][0]["kind"] != "request_evidence"
