from __future__ import annotations

import negotiation.negotiation_graph as negotiation_graph
from negotiation.executor.render_executor import build_strategy_summary
from negotiation.policies import safe_neutral_policy_id
from negotiation.schemas import default_policy_decision, default_progress_state, default_world_state
from state import SessionState

from tests.helpers.negotiation_harness import (
    ExecutorScript,
    FakeLLM,
    PlannerScript,
    assert_policy_decision_invariants,
    assert_progress_invariants,
    fake_update_belief_state,
    random_messages,
    simulate_conversation,
    trace_guard,
)


class DepsHarness:
    def __init__(self, planner, llm):
        self.plan_phase_policy = planner.plan_phase_policy
        self.update_belief_state = fake_update_belief_state
        self.execute = llm.execute
        self.set_user_message = llm.set_user_message


def _planner_response(phase: str, policy_id: str, confidence: float = 0.72):
    decision = default_policy_decision()
    decision["policy_id"] = policy_id
    return (
        {
            "phase": phase,
            "confidence": confidence,
            "reasons": ["history:script"],
            "signals": [],
            "alternatives": [],
        },
        decision,
        {"planner_meta": {"scripted": True}},
    )


def _phase_order(phase: str) -> int:
    mapping = {"climate": 0, "interests": 1, "options": 2, "adjust": 3, "formalize": 4}
    return mapping.get(phase, 0)


def _negotiation_state() -> SessionState:
    state = SessionState(user_id="u", session_id="s")
    state.progress_state = default_progress_state()
    state.progress_state["conversation_mode"] = "negotiation"
    state.progress_state["mode_confidence"] = 1.0
    return state


def _assert_trace_invariants(trace: list[dict], graph_states: list[dict]) -> None:
    assert len(trace) >= len(graph_states)
    trace_slice = trace[-len(graph_states) :] if graph_states else []
    for entry, graph_state in zip(trace_slice, graph_states):
        assert_progress_invariants(entry["progress_state"])
        allowed_ids = graph_state.get("allowed_policy_ids") or []
        assert allowed_ids
        assert_policy_decision_invariants(entry["policy_decision"], allowed_ids)


def test_e2e_happy_path_progression(monkeypatch, tmp_path):
    planner = PlannerScript(
        responses=[
            _planner_response("climate", "test_credibility"),
            _planner_response("interests", "info_extract_critical"),
            _planner_response("adjust", "hold_position"),
            _planner_response("formalize", "formalize_recap_confirm"),
        ]
    )
    executor_script = ExecutorScript()
    llm = FakeLLM(executor_script=executor_script)
    deps = DepsHarness(planner, llm)

    turns = [
        "Tengo otra oferta",
        "Tengo evidencia",
        "Detalles del otro comprador",
        "precio 12000",
        "ok",
        "vale",
    ]

    state = _negotiation_state()
    state, trace, graph_states = simulate_conversation(
        turns,
        deps,
        initial_state=state,
        monkeypatch=monkeypatch,
        graph_module=negotiation_graph,
    )

    with trace_guard(tmp_path, "happy_path", trace, graph_states):
        phases = [entry["phase_effective"]["phase"] for entry in trace]
        assert phases[0] in {"climate", "interests"}
        assert all(p in {"climate", "interests", "options", "adjust", "formalize"} for p in phases)

        policy_state_turn2 = graph_states[1]["progress_state"]["policy_state"]
        assert policy_state_turn2["step_idx"] == 1
        policy_meta_turn2 = graph_states[1]["policy_meta"]
        assert policy_meta_turn2["transition"] == "advance"
        policy_meta_turn3 = graph_states[2]["policy_meta"]
        assert policy_meta_turn3["transition"] == "succeed"
        assert "steps_completed" in policy_meta_turn3.get("reasons", [])
        planner_transitions = [
            graph_states[0]["policy_meta"]["transition"],
            graph_states[1]["policy_meta"]["transition"],
            graph_states[2]["policy_meta"]["transition"],
        ]
        assert planner_transitions == ["force_planner", "advance", "succeed"]

        assert executor_script.prompts
        prompt = executor_script.prompts[1]
        assert "policy_next_hint:" in prompt
        assert "phase_effective:" in prompt
        assert "belief_state_summary:" in prompt
        assert "interaction_health" in prompt
        assert trace[1]["phase_effective"]["phase"] in prompt

        _assert_trace_invariants(trace, graph_states)
        assert state.debug_trace


def test_e2e_no_progress_triggers_replan(monkeypatch, tmp_path):
    planner = PlannerScript(responses=[_planner_response("climate", "test_credibility")])
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)
    turns = ["tengo otra oferta"] + ["ok"] * 5

    state = _negotiation_state()
    state, trace, graph_states = simulate_conversation(
        turns,
        deps,
        initial_state=state,
        monkeypatch=monkeypatch,
        graph_module=negotiation_graph,
    )

    with trace_guard(tmp_path, "no_progress", trace, graph_states):
        assert planner.calls
        assert any(
            "attempts_or_progress_exceeded" in gs.get("policy_meta", {}).get("reasons", [])
            for gs in graph_states
        )
        assert any(gs.get("policy_meta", {}).get("transition") == "force_planner" for gs in graph_states)
        assert trace[-1]["gates"]["planner_skipped"] is False
        _assert_trace_invariants(trace, graph_states)
        assert state.debug_trace


def test_e2e_bad_inputs_no_crash(monkeypatch, tmp_path):
    planner = PlannerScript(responses=[_planner_response("climate", "safe_neutral")])
    llm = FakeLLM(executor_script=ExecutorScript(outputs=["{not-json"]))
    deps = DepsHarness(planner, llm)
    turns = [
        "",
        "x" * 20050,
        "🙂" * 40,
        "1234567890",
        "Hola — hello — こんにちは",
        "markdown **bold** `code`\n\n- item\n- item2",
    ]

    _state, trace, graph_states = simulate_conversation(
        turns, deps, monkeypatch=monkeypatch, graph_module=negotiation_graph
    )

    with trace_guard(tmp_path, "bad_inputs", trace, graph_states):
        last = trace[-1]
        _assert_trace_invariants(trace, graph_states)
        assert len(last["progress_state"]["policy_state"]["slots_required"]) <= 12
        confidence = float(last["phase_effective"].get("confidence", 0.0))
        assert 0.0 <= confidence <= 1.0


def test_e2e_corrupted_state_normalized(monkeypatch, tmp_path):
    planner = PlannerScript(responses=[_planner_response("climate", "safe_neutral")])
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)
    state = SessionState(user_id="u", session_id="s")
    state.world_state = {"negotiation": "oops"}
    state.belief_state = {"universal": "bad"}
    state.progress_state = {
        "policy_state": {"status": "weird", "step_idx": "x", "planner_request": "bad"},
        "phase_state": {"phase": "unknown", "confidence": 3},
        "gate_state": {"allowed_ids_hash_stable_count": -3},
    }

    _state, trace, graph_states = simulate_conversation(
        ["hola"], deps, initial_state=state, monkeypatch=monkeypatch, graph_module=negotiation_graph
    )

    with trace_guard(tmp_path, "corrupted_state", trace, graph_states):
        last = trace[-1]
        assert last["validation_issues"]["progress_in"]
        _assert_trace_invariants(trace, graph_states)


def test_e2e_planner_defective_outputs(monkeypatch, tmp_path):
    bad_policy = (
        {"phase": "invalid_phase", "confidence": 2.2, "reasons": ["x"], "signals": []},
        {"policy_id": "not_real", "reason": "??", "risk_posture": "highish"},
        {"planner_meta": {"scripted": True}},
    )
    planner = PlannerScript(
        responses=[
            bad_policy,
            Exception("planner boom"),
        ]
    )
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)
    turns = ["otra oferta", "otra oferta"]

    _state, trace, graph_states = simulate_conversation(
        turns, deps, monkeypatch=monkeypatch, graph_module=negotiation_graph
    )

    with trace_guard(tmp_path, "planner_defective", trace, graph_states):
        first = graph_states[0]
        assert first["planner_meta"].get("policy_normalization_changed", False) is True
        assert first["phase_effective"]["phase"] in {"climate", "interests"}
        assert_policy_decision_invariants(first["policy_decision"], first["allowed_policy_ids"])

        second = graph_states[1]
        assert second["planner_meta"]["planner_failed"] is True
        assert second["planner_meta"]["planner_fallback_used"] is True
        assert second["policy_decision"]["policy_id"] == safe_neutral_policy_id()


def test_e2e_phase_hysteresis_hold(monkeypatch, tmp_path):
    planner = PlannerScript(
        responses=[
            _planner_response("formalize", "safe_neutral", confidence=0.4),
            _planner_response("formalize", "safe_neutral", confidence=0.4),
        ]
    )
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)

    _state, trace, graph_states = simulate_conversation(
        ["hola", "hola"], deps, monkeypatch=monkeypatch, graph_module=negotiation_graph
    )

    with trace_guard(tmp_path, "hysteresis", trace, graph_states):
        assert graph_states[0]["phase_meta"]["phase_hysteresis_held"] is True
        assert graph_states[0]["phase_effective"]["phase"] == "climate"
        assert graph_states[1]["phase_meta"]["phase_hysteresis_held"] is True
        assert graph_states[1]["phase_effective"]["phase"] == "climate"
        _assert_trace_invariants(trace, graph_states)


def test_e2e_continue_policy_skips_planner(monkeypatch, tmp_path):
    planner = PlannerScript(responses=[Exception("planner should not be called")])
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)
    state = SessionState(user_id="u", session_id="s")
    state.world_state = default_world_state()
    state.world_state["negotiation"]["other_buyer_claimed"] = True
    progress = default_progress_state()
    progress["policy_state"] = {
        "status": "active",
        "policy_id": "test_credibility",
        "step_idx": 0,
        "step_attempts": 0,
        "max_attempts_per_step": 2,
        "started_turn": 0,
        "last_turn": 0,
        "no_progress_turns": 0,
        "planner_request": "continue_policy",
        "slots_required": ["negotiation.other_buyer_text", "negotiation.evidence_offered"],
        "slots_filled": {},
    }
    state.progress_state = progress

    _state, trace, graph_states = simulate_conversation(
        ["ok"], deps, initial_state=state, monkeypatch=monkeypatch, graph_module=negotiation_graph
    )

    with trace_guard(tmp_path, "continue_skip", trace, graph_states):
        meta = graph_states[0]["planner_meta"]
        assert meta["planner_skipped"] is True
        assert meta["planner_skip_reason"] == "continue_policy"
        assert graph_states[0]["phase_effective"]["phase"] == "climate"
        _assert_trace_invariants(trace, graph_states)


def test_e2e_choose_and_replan_calls_planner(monkeypatch, tmp_path):
    planner = PlannerScript(
        responses=[
            _planner_response("climate", "test_credibility"),
            _planner_response("climate", "safe_neutral"),
        ]
    )
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)
    state = SessionState(user_id="u", session_id="s")
    state.progress_state = default_progress_state()

    _state, trace, graph_states = simulate_conversation(
        ["hola"], deps, initial_state=state, monkeypatch=monkeypatch, graph_module=negotiation_graph
    )
    state.progress_state["policy_state"] = {
        "status": "active",
        "policy_id": "test_credibility",
        "step_idx": 99,
        "step_attempts": 0,
        "max_attempts_per_step": 2,
        "started_turn": 0,
        "last_turn": 0,
        "no_progress_turns": 0,
        "planner_request": "continue_policy",
        "slots_required": ["negotiation.other_buyer_text", "negotiation.evidence_offered"],
        "slots_filled": {},
    }

    _state, trace2, graph_states2 = simulate_conversation(
        ["hola"], deps, initial_state=state, monkeypatch=monkeypatch, graph_module=negotiation_graph
    )

    combined_trace = trace + trace2
    combined_graph_states = graph_states + graph_states2
    with trace_guard(tmp_path, "choose_replan", combined_trace, combined_graph_states):
        assert len(planner.calls) == 2
        assert graph_states[0]["planner_meta"]["planner_skipped"] is False
        assert graph_states2[0]["planner_meta"]["planner_skipped"] is False
        _assert_trace_invariants(trace, graph_states)
        _assert_trace_invariants(trace2[-len(graph_states2):], graph_states2)


def test_e2e_policy_required_inputs_gate(monkeypatch, tmp_path):
    planner = PlannerScript(responses=[_planner_response("climate", "safe_neutral")])
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)

    state = _negotiation_state()
    _state, trace, graph_states = simulate_conversation(
        ["hola", "precio 12000"],
        deps,
        initial_state=state,
        monkeypatch=monkeypatch,
        graph_module=negotiation_graph,
    )

    with trace_guard(tmp_path, "required_inputs", trace, graph_states):
        first_allowed = graph_states[0]["allowed_policy_ids"]
        second_allowed = graph_states[1]["allowed_policy_ids"]
        assert "tradeoff_offer" not in first_allowed
        assert "tradeoff_offer" not in second_allowed
        _assert_trace_invariants(trace, graph_states)


def test_e2e_planner_policy_not_allowed_falls_back(monkeypatch, tmp_path):
    planner = PlannerScript(responses=[_planner_response("climate", "test_credibility")])
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)

    _state, trace, graph_states = simulate_conversation(
        ["hola"],
        deps,
        initial_state=_negotiation_state(),
        monkeypatch=monkeypatch,
        graph_module=negotiation_graph,
    )

    with trace_guard(tmp_path, "policy_not_allowed", trace, graph_states):
        first_allowed = graph_states[0]["allowed_policy_ids"]
        assert "test_credibility" not in first_allowed
        assert graph_states[0]["planner_meta"]["policy_normalization_changed"] is True
        assert graph_states[0]["policy_decision"]["policy_id"] in first_allowed
        _assert_trace_invariants(trace, graph_states)


def test_e2e_boolean_slot_false_not_counted(monkeypatch, tmp_path):
    planner = PlannerScript(responses=[_planner_response("climate", "test_credibility")])
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)
    state = _negotiation_state()
    state.world_state = default_world_state()
    state.world_state["negotiation"]["other_buyer_claimed"] = True
    state.progress_state["policy_state"] = {
        "status": "active",
        "policy_id": "test_credibility",
        "step_idx": 0,
        "step_attempts": 0,
        "max_attempts_per_step": 2,
        "started_turn": 0,
        "last_turn": 0,
        "no_progress_turns": 0,
        "planner_request": "continue_policy",
        "slots_required": ["negotiation.evidence_offered"],
        "slots_filled": {},
    }

    _state, trace, graph_states = simulate_conversation(
        ["ok"],
        deps,
        initial_state=state,
        monkeypatch=monkeypatch,
        graph_module=negotiation_graph,
    )

    with trace_guard(tmp_path, "bool_slot_false", trace, graph_states):
        slots_filled = graph_states[0]["progress_state"]["policy_state"]["slots_filled"]
        assert "negotiation.evidence_offered" not in slots_filled
        assert graph_states[0]["progress_state"]["policy_state"]["step_idx"] == 0
        _assert_trace_invariants(trace, graph_states)


def test_e2e_executor_invalid_json_no_step_advance(monkeypatch, tmp_path):
    planner = PlannerScript(responses=[_planner_response("climate", "test_credibility")])
    executor_script = ExecutorScript(outputs=["{bad json"] * 3)
    llm = FakeLLM(executor_script=executor_script)
    deps = DepsHarness(planner, llm)

    _state, trace, graph_states = simulate_conversation(
        ["ok", "ok", "ok"],
        deps,
        initial_state=_negotiation_state(),
        monkeypatch=monkeypatch,
        graph_module=negotiation_graph,
    )

    with trace_guard(tmp_path, "executor_invalid_json", trace, graph_states):
        step_idxs = [gs["progress_state"]["policy_state"]["step_idx"] for gs in graph_states]
        assert step_idxs == sorted(step_idxs)
        assert all(step_idx == 0 for step_idx in step_idxs)
        assert all(gs["policy_meta"]["transition"] != "advance" for gs in graph_states)
        _assert_trace_invariants(trace, graph_states)


def test_intent_hint_compat_priority():
    state = {
        "policy_decision": {"micro_goal": "x", "risk_posture": "low", "why_short": "", "inputs_used": []},
        "policy_hint": {"next_action_hint": "policy hint"},
        "intent_hint": {"next_action_hint": "intent hint"},
        "progress_state": {"phase_state": {"phase": "opening"}},
    }
    summary = build_strategy_summary(state, "general", "universal", "safe_neutral")
    assert summary["policy_next_hint"] == "policy hint"

    state["policy_hint"] = {}
    summary = build_strategy_summary(state, "general", "universal", "safe_neutral")
    assert summary["policy_next_hint"] == "intent hint"


def test_planner_does_not_use_rag(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_policy_tactics",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("rag should not be called")),
    )
    planner = PlannerScript(responses=[_planner_response("climate", "safe_neutral")])
    llm = FakeLLM(executor_script=ExecutorScript())
    deps = DepsHarness(planner, llm)

    _state, trace, graph_states = simulate_conversation(
        ["hola"], deps, monkeypatch=monkeypatch, graph_module=negotiation_graph
    )

    with trace_guard(tmp_path, "no_rag", trace, graph_states):
        assert graph_states[0]["planner_meta"]["planner_failed"] is False
        _assert_trace_invariants(trace, graph_states)


def test_e2e_monkey_run_randomized(monkeypatch, tmp_path):
    planner = PlannerScript()
    executor_script = ExecutorScript(outputs=["{bad json"] * 5)
    llm = FakeLLM(executor_script=executor_script)
    deps = DepsHarness(planner, llm)

    def planner_script(**_kwargs):
        if len(planner.calls) % 2 == 0:
            return _planner_response("climate", "safe_neutral")
        return (
            {"phase": "closing", "confidence": -1, "reasons": ["x"], "signals": []},
            {"policy_id": "bad_id", "reason": "x", "risk_posture": "low"},
            {"planner_meta": {"scripted": True}},
        )

    planner.responses = [planner_script] * 50
    turns = random_messages(7, 60)

    _state, trace, graph_states = simulate_conversation(
        turns, deps, monkeypatch=monkeypatch, graph_module=negotiation_graph
    )

    with trace_guard(tmp_path, "monkey_run", trace, graph_states):
        last = trace[-1]
        _assert_trace_invariants(trace, graph_states)
        assert len(trace) == len(turns)
        assert planner.calls


def test_e2e_bluff_drives_epistemic_contract_under_flags(monkeypatch, tmp_path):
    monkeypatch.setenv("BELIEF_GOVERNOR_ENABLED", "1")
    monkeypatch.setenv("EXECUTOR_EPISTEMIC_CONTRACT_ENABLED", "1")

    planner = PlannerScript(responses=[_planner_response("climate", "safe_neutral")])
    executor_script = ExecutorScript()
    llm = FakeLLM(executor_script=executor_script)
    deps = DepsHarness(planner, llm)

    state = _negotiation_state()
    state, trace, graph_states = simulate_conversation(
        ["Tengo otro comprador pero sin pruebas"],
        deps,
        initial_state=state,
        monkeypatch=monkeypatch,
        graph_module=negotiation_graph,
    )

    with trace_guard(tmp_path, "epistemic_contract", trace, graph_states):
        assert executor_script.prompts
        prompt = executor_script.prompts[-1]
        assert "EPISTEMIC CONTRACT" in prompt
        assert "verify_first" in prompt
        assert "must_hedge" in prompt
