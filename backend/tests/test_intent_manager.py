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
    assert meta["intent_decision"] == "commit"


def test_intent_persists_across_turns_and_advances_step():
    world = default_world_state()
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar datos críticos",
            "intent_type": "info_extract",
            "steps": ["ask_open", "narrow"],
            "step_idx": 0,
            "step_attempts": 1,
            "max_attempts_per_step": 2,
            "slots": {"slots_required": ["price"], "slots_optional": [], "slots_filled": {}},
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

    assert updated["status"] == "active"
    assert updated["step_idx"] == 1
    assert updated["step_attempts"] == 0
    assert hint["step_name"] == "narrow"
    assert meta["intent_decision"] == "advance"


def test_intent_succeeds_when_slots_complete():
    world = default_world_state()
    world["price_mentioned"] = True
    world["price_value"] = 9500
    belief = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_goal": "Cerrar precio",
            "intent_type": "closing",
            "steps": ["summarize"],
            "step_idx": 0,
            "slots": {"slots_required": ["price"], "slots_optional": [], "slots_filled": {}},
        }
    )

    updated, meta, hint = update_intent_state(
        prev_intent=intent,
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        user_message="precio 9500",
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
            "steps": ["ask_open"],
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
        "step_name": "deescalate",
        "commitment_level": "hard",
    }

    constrained, preferred, meta = apply_intent_constraints(allowed, intent_hint)

    assert preferred == ["deescalate_tension"]
    assert constrained == ["deescalate_tension"]
    assert meta["planner_mode"] == "intent_forced"
