from types import SimpleNamespace

from negotiation.nodes.executor_node import executor_node
from negotiation.nodes.planner_node import phase_policy_planner_node
from negotiation.policy_progress import update_policy_state
from negotiation.progress_updater import update_progress_state
from negotiation.schemas import (
    default_belief_state,
    default_policy_decision,
    default_policy_state,
    default_progress_state,
    default_world_state,
)
from negotiation.world_state_updater import update_world_state
from negotiation.state.deps import AgentDeps


class _QueueDeps:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    def execute(self, _messages):
        return self.payloads.pop(0)


def _active_plan():
    return {
        "plan_id": "p1",
        "current_step_idx": 0,
        "steps": [
            {
                "step_idx": 0,
                "intent_id": "collect_maintenance",
                "what_to_do": "confirmar mantenimiento",
                "safe_mode": "normal",
                "ask": ["¿Qué mantenimiento concreto puedes confirmar?"],
            },
            {"step_idx": 1, "intent_id": "pivot", "what_to_do": "pivot", "safe_mode": "normal", "ask": []},
        ],
        "plan_constraints": {"max_questions_per_turn": 1, "must_avoid": [], "stop_conditions": []},
    }


def test_integration_c1_mantenimiento_y_oferta_sin_repeticion_literal(monkeypatch):
    deps = _QueueDeps([
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"claims":[{"text":"Mantenimiento aceite, ruedas y electrónica","confidence":0.82,"raw_text":"aceite/ruedas/electrónica","source_turn":1}],"offers":[{"text":"Se compromete a dejarlo por escrito","confidence":0.86,"raw_text":"me comprometo a dejarlo por escrito","source_turn":1}],"requests":[],"concessions":[],"constraints":[],"interests":[],"context":[]},"meta":{}}'
    ])
    world, _ = update_world_state(default_world_state(), "aceite/ruedas/electrónica y me comprometo a dejarlo por escrito", turn_count=1, deps=deps)
    assert world["world_buckets"]["claims"]
    assert world["world_buckets"]["offers"]

    def fake_render(*_args, **_kwargs):
        return {"response_text": "¿Qué mantenimiento concreto puedes confirmar?", "asked_question": True}

    monkeypatch.setattr("negotiation.nodes.executor_node.render_executor_output", fake_render)
    state = {
        "deps": AgentDeps(plan_phase_policy=lambda **_: ({}, default_policy_decision(), {}), update_belief_state=lambda **_: (default_belief_state(), {}), execute=lambda _m: "ok"),
        "objective": "x",
        "user_message": "detalle entregado",
        "policy_decision": default_policy_decision(),
        "progress_state": default_progress_state(),
        "world_state": world,
        "policy_plan_judgement": {"plan_status": "continue_same_step", "missing_signals": []},
    }
    state["progress_state"]["active_plan"] = _active_plan()
    state["progress_state"]["plan_ledger"]["asked_questions_recent"] = ["¿Qué mantenimiento concreto puedes confirmar?"]
    out = executor_node(state)
    assert out["assistant_message"] == "¿Qué mantenimiento concreto puedes confirmar?"


def test_integration_c2_loop_3_intentos_no_fuerza_replan_por_attempts(monkeypatch):
    progress = default_progress_state()
    progress["active_plan"] = _active_plan()

    for turn in [1, 2, 3]:
        progress["last_judgement_status"] = "continue_same_step"
        progress = update_progress_state(
            prev_progress=progress,
            policy_decision=default_policy_decision(),
            last_policy_executed=None,
            prev_world_state=default_world_state(),
            world_state=default_world_state(),
            prev_belief_state=default_belief_state(),
            belief_state=default_belief_state(),
            turn_count=turn,
            policy_plan_judgement={"plan_status": "continue_same_step", "evidence": [{"quote": "respuesta en línea"}]},
            active_plan=_active_plan(),
        )

    pstate, _, meta = update_policy_state(
        prev_policy_state={**default_policy_state(), "planner_request": "continue_policy", "policy_id": "safe_neutral"},
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        belief_diff={},
        progress_state=progress,
        user_message="",
        turn_count=4,
        policy_plan_judgement={"plan_status": "continue_same_step"},
    )
    assert pstate["planner_request"] == "continue_policy"


def test_integration_c3_human_desvio_un_turno_y_retorno_sin_replan(monkeypatch):
    def fake_render(*_args, **_kwargs):
        return {
            "response_text": "Estoy bien, gracias. Volviendo al punto, ¿Cuántos propietarios ha tenido?",
            "asked_question": True,
        }

    monkeypatch.setattr("negotiation.nodes.executor_node.render_executor_output", fake_render)
    state = {
        "deps": SimpleNamespace(execute=lambda _m: "ok"),
        "objective": "x",
        "user_message": "¿Cómo estás?",
        "policy_decision": default_policy_decision(),
        "progress_state": default_progress_state(),
        "world_state": default_world_state(),
        "policy_plan_judgement": {"plan_status": "continue_same_step", "skip_planner": True},
        "advisor_recs": {"human_mode": "answer_then_bridge", "answer_focus": "Estoy bien, gracias.", "bridge": "Volviendo al punto,"},
    }
    state["progress_state"]["active_plan"] = {
        "plan_id": "p1",
        "current_step_idx": 0,
        "steps": [{"step_idx": 0, "ask": ["¿Cuántos propietarios ha tenido?"], "intent_id": "owners"}],
    }
    out = executor_node(state)
    assert "Estoy bien" in out["assistant_message"]
    assert out["assistant_message"].endswith("¿Cuántos propietarios ha tenido?")
    assert state["policy_plan_judgement"]["plan_status"] == "continue_same_step"
