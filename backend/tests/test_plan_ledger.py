from types import SimpleNamespace

from negotiation.nodes.planner_node import phase_policy_planner_node, validate_active_plan_against_ledger
from negotiation.progress_updater import update_progress_state
from negotiation.schemas import default_belief_state, default_policy_decision, default_progress_state, default_world_state


def _base_plan(intent_id: str = "owner_history"):
    return {
        "plan_id": "p1",
        "current_step_idx": 0,
        "steps": [
            {
                "step_idx": 0,
                "intent_id": intent_id,
                "micro_goal": "Confirmar historia de propiedad",
                "what_to_do": "Haz una pregunta concreta",
                "ask": ["¿Cuántos dueños tuvo?"],
                "success_criteria": ["historia_propiedad_aclarada"],
                "safe_mode": "normal",
            }
        ],
    }


def _update(prev_progress, judgement, turn=1, user_message="sí, fue único dueño", last_assistant="¿Cuántos dueños tuvo?"):
    progress = dict(prev_progress)
    progress["active_plan"] = _base_plan("owner_history")
    return update_progress_state(
        prev_progress=progress,
        policy_decision=default_policy_decision(),
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        turn_count=turn,
        policy_plan_judgement=judgement,
        user_message=user_message,
        active_plan=progress["active_plan"],
        last_assistant_message=last_assistant,
    )


def test_ledger_advance_adds_resolved_with_evidence():
    progress = default_progress_state()
    out = _update(progress, {"plan_status": "advance_step", "evidence": [{"quote": "único dueño"}]})
    resolved = out["plan_ledger"]["resolved_intents"]
    assert resolved and resolved[0]["intent_id"] == "owner_history"
    assert "único dueño" in resolved[0]["evidence"]


def test_ledger_continue_increments_attempt_counters():
    progress = default_progress_state()
    out = _update(progress, {"plan_status": "continue_same_step", "why": "sin detalle"})
    assert out["plan_ledger"]["attempt_counters"]["owner_history"] == 1


def test_ledger_continue_twice_adds_failed_intent():
    progress = default_progress_state()
    out1 = _update(progress, {"plan_status": "continue_same_step", "why": "vago"}, turn=1)
    out2 = _update(out1, {"plan_status": "continue_same_step", "why": "sigue vago"}, turn=2)
    failed = out2["plan_ledger"]["failed_intents"]
    assert failed and failed[0]["intent_id"] == "owner_history"
    assert failed[0]["attempts"] >= 2


def test_ledger_questions_recent_dedup_and_cap_10():
    progress = default_progress_state()
    out = progress
    for i in range(12):
        q = f"¿Pregunta {i}?"
        out = _update(out, {"plan_status": "continue_same_step", "why": "x"}, turn=i + 1, last_assistant=q)
    recent = out["plan_ledger"]["asked_questions_recent"]
    assert len(recent) == 10
    out2 = _update(out, {"plan_status": "continue_same_step", "why": "x"}, turn=20, last_assistant="¿Pregunta 11?")
    assert out2["plan_ledger"]["asked_questions_recent"].count("¿Pregunta 11?") == 1


def test_ledger_resolved_dedup_intent_id():
    progress = default_progress_state()
    out1 = _update(progress, {"plan_status": "advance_step", "evidence": [{"quote": "e1"}]}, turn=1)
    out2 = _update(out1, {"plan_status": "completed", "evidence": [{"quote": "e2"}]}, turn=2)
    resolved = [x for x in out2["plan_ledger"]["resolved_intents"] if x["intent_id"] == "owner_history"]
    assert len(resolved) == 1
    assert resolved[0]["evidence"] == "e2"


def test_validate_plan_rejects_resolved_intent():
    plan = {"steps": [{"intent_id": "owner_history"}]}
    ledger = {"resolved_intents": [{"intent_id": "owner_history"}]}
    ok, errors = validate_active_plan_against_ledger(plan, ledger)
    assert ok is False
    assert any("intent_already_resolved:owner_history" in e for e in errors)


def test_validate_plan_rejects_duplicated_intent_ids():
    plan = {"steps": [{"intent_id": "a"}, {"intent_id": "a"}]}
    ok, errors = validate_active_plan_against_ledger(plan, {"resolved_intents": []})
    assert ok is False
    assert any("duplicate_intent_id:a" in e for e in errors)


def test_integration_planner_rejects_plan_with_resolved_intent():
    progress_state = default_progress_state()
    progress_state["policy_state"]["planner_request"] = "replan_policy"
    progress_state["plan_ledger"]["resolved_intents"] = [{"intent_id": "owner_history", "evidence": "ok", "turn_idx": 2}]

    def fake_plan_phase_policy(**_kwargs):
        return (
            {"phase": "interests"},
            {"policy_id": "safe_neutral"},
            {
                "active_plan": {
                    "plan_id": "p2",
                    "current_step_idx": 0,
                    "steps": [
                        {
                            "step_idx": 0,
                            "intent_id": "owner_history",
                            "micro_goal": "repetido",
                            "what_to_do": "repetir",
                            "ask": ["¿dueños?"],
                            "success_criteria": ["historia_propiedad_aclarada"],
                            "safe_mode": "normal",
                        }
                    ],
                }
            },
        )

    state = {
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "progress_state": progress_state,
        "objective": "",
        "constraints": "",
        "hard_constraints_struct": {},
        "recent_history_text": "",
        "turn_count": 4,
        "world_diff": {},
        "belief_diff": {},
        "allowed_policy_ids": ["safe_neutral"],
        "deps": SimpleNamespace(plan_phase_policy=fake_plan_phase_policy),
    }

    out = phase_policy_planner_node(state)
    assert out["planner_meta"].get("planner_error") in {"invalid_plan_against_ledger", "invalid_fallback_plan_against_ledger"}
    assert out["planner_meta"].get("planner_fallback_used") is True
