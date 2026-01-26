from negotiation.intent_manager import update_intent_state
from negotiation.policy_planner import apply_intent_constraints
from negotiation.schemas import default_belief_state, default_intent_state, default_progress_state
from negotiation.schemas import default_world_state


def test_intent_starts_when_requires_multi_turn():
    world = default_world_state()
    belief = default_belief_state()
    progress = default_progress_state()
    intent, meta, hint = update_intent_state(
        prev_intent=default_intent_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="depende, ya veremos",
        turn_count=1,
    )

    assert intent["status"] == "active"
    assert intent["steps"]
    assert hint["intent_active"] is True
    assert hint["step_kind"]
    assert meta["intent_decision"] == "commit"


def test_intent_does_not_start_when_one_turn_sufficient():
    world = default_world_state()
    world["price_mentioned"] = True
    world["price_value"] = 9000
    belief = default_belief_state()
    progress = default_progress_state()

    updated, meta, _hint = update_intent_state(
        prev_intent=default_intent_state(),
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="precio 9000",
        turn_count=2,
    )

    assert updated["status"] == "inactive"
    assert meta["intent_decision"] == "inactive"


def test_step_advances_only_when_target_slot_progresses():
    world = default_world_state()
    world["evidence_offered"] = True
    world["evidence_text"] = "tengo factura"
    belief = default_belief_state()
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
                },
                {
                    "kind": "probe_narrow",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                },
            ],
            "step_idx": 0,
            "step_attempts": 0,
            "max_attempts_per_step": 2,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="tengo factura",
        turn_count=2,
    )

    assert updated["status"] == "active"
    assert updated["step_idx"] == 0
    assert meta["intent_decision"] == "continue"


def test_intent_succeeds_when_slots_complete():
    world = default_world_state()
    world["price_mentioned"] = True
    world["price_value"] = 9500
    world["price_firm"] = True
    world["price_firm_text"] = "precio fijo"
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Cerrar precio",
            "intent_type": "closing",
            "steps": [
                {"kind": "close_next", "target_slot": "price_firm", "success_if_filled": ["price_firm"]}
            ],
            "step_idx": 0,
            "slots": {
                "slots_required": ["price", "price_firm"],
                "slots_optional": [],
                "slots_filled": {},
            },
            "success_criteria": ["slots_required_complete", "firm_price_detected"],
        }
    )

    updated, meta, hint = update_intent_state(
        prev_intent=intent,
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="precio fijo 9500",
        turn_count=3,
    )

    assert updated["status"] == "succeeded"
    assert meta["intent_decision"] == "succeed"
    assert hint["intent_active"] is False


def test_intent_abandons_on_hard_trigger():
    world = default_world_state()
    belief = default_belief_state()
    belief["dynamics"]["interaction_health"] = "tense"
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Extraer información",
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

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="",
        turn_count=4,
    )

    assert updated["status"] == "abandoned"
    assert "interaction_tense" in updated["abandon_reasons"]
    assert meta["intent_decision"] == "abandon"


def test_planner_respects_intent_hard_preferences():
    allowed = ["info_extract_critical", "rapport_build", "deescalate_tension"]
    intent_hint = {
        "step_kind": "pressure_soft",
        "commitment_level": "hard",
    }

    constrained, preferred, meta = apply_intent_constraints(allowed, intent_hint)

    assert "deescalate_tension" in preferred
    assert constrained == ["deescalate_tension"]
    assert meta["planner_mode"] == "intent_forced"


def test_vague_response_triggers_pivot_sequence():
    world = default_world_state()
    belief = default_belief_state()
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
                },
                {
                    "kind": "probe_narrow",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                },
                {
                    "kind": "trade_incentive",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                },
            ],
            "step_idx": 0,
            "step_attempts": 0,
            "max_attempts_per_step": 2,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, hint = update_intent_state(
        prev_intent=intent,
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="no sé",
        turn_count=2,
    )

    assert updated["step_idx"] == 0
    assert meta["intent_decision"] == "continue"

    updated, meta, hint = update_intent_state(
        prev_intent=updated,
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="depende",
        turn_count=3,
    )

    assert updated["step_idx"] == 1
    assert hint["step_kind"] == "probe_narrow"
    assert meta["intent_decision"] == "pivot"
    assert meta["pivot_reason"] == "vague_response"


def test_replan_transition_when_price_firm_detected():
    world = default_world_state()
    world["price_firm"] = True
    world["price_firm_text"] = "precio fijo"
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Extraer información",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "slots": {"slots_required": ["seller_batna"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="precio fijo",
        turn_count=5,
    )

    assert updated["status"] == "active"
    assert updated["intent_type"] == "closing"
    assert meta["intent_decision"] == "replan"
    assert meta["intent_transition"] == "replan_to:closing"
