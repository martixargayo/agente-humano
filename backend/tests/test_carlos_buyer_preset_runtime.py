from __future__ import annotations

import negotiation.negotiation_graph as negotiation_graph
from negotiation.elementos.render.preset_registry import apply_buyer_preset_to_render_state
from negotiation.schemas import default_progress_state
from state import SessionState

from tests.helpers.negotiation_harness import (
    ExecutorScript,
    FakeLLM,
    PlannerScript,
    capture_graph_states,
    fake_update_belief_state,
    simulate_conversation,
)


class DepsHarness:
    def __init__(self, planner, llm):
        self.plan_phase_policy = planner.plan_phase_policy
        self.update_belief_state = fake_update_belief_state
        self.execute = llm.execute
        self.set_user_message = llm.set_user_message


def _planner_response(phase: str, policy_id: str, confidence: float = 0.8):
    return (
        {
            "phase": phase,
            "confidence": confidence,
            "reasons": ["scripted"],
            "signals": [],
            "alternatives": [],
        },
        {
            "policy_id": policy_id,
            "reason": "scripted",
            "micro_goal": "seguir",
            "risk_posture": "low",
            "capabilities": None,
            "why_short": "",
            "inputs_used": [],
        },
        {"planner_meta": {"scripted": True}},
    )


def _negotiation_state() -> SessionState:
    state = SessionState(user_id="u", session_id="preset")
    state.progress_state = default_progress_state()
    state.progress_state["conversation_mode"] = "negotiation"
    state.progress_state["mode_confidence"] = 1.0
    return state


def test_apply_buyer_preset_sets_expected_render_shape() -> None:
    progress = default_progress_state()
    updated, meta = apply_buyer_preset_to_render_state(progress, "carlos", preset_source="explicit")

    assert meta["buyer_preset_applied"] is True
    assert meta["buyer_preset_source"] == "explicit"
    assert updated["render_state"]["persona_id"] == "buyer_mustang67_v1"
    assert updated["render_state"]["scene_id"] == "mustang67_in_person_viewing"
    assert updated["render_state"]["style_id"] == "psyplay_compact"
    assert updated["render_state"]["buyer_preset_id"] == "carlos"


def test_apply_buyer_preset_partial_render_state_does_not_block() -> None:
    progress = default_progress_state()
    progress["render_state"] = {}

    updated, meta = apply_buyer_preset_to_render_state(progress, "carlos", preset_source="env")

    assert meta["buyer_preset_applied"] is True
    assert meta["buyer_preset_error"] == ""
    assert updated["render_state"]["persona_id"] == "buyer_mustang67_v1"


def test_apply_buyer_preset_env_does_not_override_custom_render_state() -> None:
    progress = default_progress_state()
    progress["render_state"] = {
        "persona_id": "avatar_sales",
        "scene_id": "in_person_negotiation",
        "style_id": "concise",
    }

    updated, meta = apply_buyer_preset_to_render_state(progress, "carlos", preset_source="env")

    assert meta["buyer_preset_applied"] is False
    assert meta["buyer_preset_error"] == "render_state_already_customized"
    assert updated["render_state"]["persona_id"] == "avatar_sales"


def test_apply_buyer_preset_explicit_overrides_custom_render_state() -> None:
    progress = default_progress_state()
    progress["render_state"] = {
        "persona_id": "avatar_sales",
        "scene_id": "in_person_negotiation",
        "style_id": "concise",
    }

    updated, meta = apply_buyer_preset_to_render_state(
        progress,
        "carlos",
        override_existing=True,
        preset_source="explicit",
    )

    assert meta["buyer_preset_applied"] is True
    assert meta["buyer_preset_source"] == "explicit"
    assert updated["render_state"]["persona_id"] == "buyer_mustang67_v1"


def test_e2e_runtime_env_preset_applies_to_executor(monkeypatch):
    monkeypatch.setenv("NEGOTIATION_BUYER_PRESET", "carlos")
    planner = PlannerScript(responses=[_planner_response("climate", "safe_neutral")])
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)

    state = _negotiation_state()
    _, _, graph_states = simulate_conversation(
        ["Hola, ¿podemos ver el coche?"],
        deps,
        initial_state=state,
        monkeypatch=monkeypatch,
        graph_module=negotiation_graph,
    )

    last_state = graph_states[-1]
    meta = last_state["executor_render_meta"]
    assert meta["persona_id"] == "buyer_mustang67_v1"
    assert meta["scene_id"] == "mustang67_in_person_viewing"
    assert meta["style_id"] == "psyplay_compact"


def test_e2e_explicit_preset_overrides_env_and_reaches_executor(monkeypatch):
    monkeypatch.setenv("NEGOTIATION_BUYER_PRESET", "")
    planner = PlannerScript(responses=[_planner_response("climate", "safe_neutral")])
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)

    state = _negotiation_state()
    state.progress_state["render_state"] = {
        "persona_id": "avatar_sales",
        "scene_id": "in_person_negotiation",
        "style_id": "concise",
    }

    with capture_graph_states(monkeypatch, negotiation_graph) as captured:
        deps.set_user_message("hola")
        negotiation_graph.run_negotiation_agent(
            state,
            "Hola, quiero hablar del Mustang",
            deps=deps,
            explicit_preset_id="carlos",
        )

    last_state = captured[-1]
    meta = last_state["executor_render_meta"]
    assert meta["persona_id"] == "buyer_mustang67_v1"
    assert meta["scene_id"] == "mustang67_in_person_viewing"
    assert meta["style_id"] == "psyplay_compact"
