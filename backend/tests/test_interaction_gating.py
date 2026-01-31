from negotiation.gate_utils import input_shape_features, precedence_signature, stable_allowed_ids_hash
from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_policy_decision, default_progress_state, default_world_state
from negotiation.world_state_updater import extract_interaction_signals
from state import SessionState


def _fake_deps(plan_phase_policy):
    def fake_update_belief_state(*_args, **_kwargs):
        return default_belief_state(), {"belief_update_skipped": False}

    def fake_execute(_messages):
        return "ok"

    return AgentDeps(
        plan_phase_policy=plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )


def test_negated_acceptance_does_not_trigger():
    prev_world = default_world_state()
    for message in ("no me parece bien", "vale, pero no", "ok, no"):
        interaction = extract_interaction_signals(message, prev_world)
        assert interaction["implicit_acceptance"] is False


def test_no_refresh_storms_on_ack_sequence(monkeypatch):
    planner_calls = {"count": 0}

    def fake_plan_phase_policy(*_args, **_kwargs):
        planner_calls["count"] += 1
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, default_policy_decision(), {}

    llm_calls = {"count": 0}

    def fake_extract_state_patch_llm(*_args, **_kwargs):
        llm_calls["count"] += 1
        raise AssertionError("LLM extractor should not be called for short acks.")

    deps = _fake_deps(fake_plan_phase_policy)
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "true")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    monkeypatch.setenv("WORLD_REFRESH_INTERVAL_TURNS", "50")
    monkeypatch.setenv("PHASE_POLICY_REFRESH_INTERVAL_TURNS", "20")
    monkeypatch.setenv("BELIEF_REFRESH_INTERVAL_TURNS", "20")
    monkeypatch.setattr(
        "negotiation.world_state_updater.extract_state_patch_llm",
        fake_extract_state_patch_llm,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.allowed_policy_ids",
        lambda *_a, **_k: ["rapport_build"],
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.compute_precedence",
        lambda *_a, **_k: type(
            "Prec",
            (),
            {
                "mode": "opening_or_other",
                "reason": "test",
                "min_policy_tags": set(),
                "block_policy_tags": set(),
                "phase_floor": None,
                "allow_closing": True,
            },
        )(),
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.update_intent_state",
        lambda **_k: (default_progress_state().get("intent_state"), {"intent_transition": "none"}, {}),
    )
    def fake_update_progress_state(**kwargs):
        prev_progress = kwargs.get("prev_progress")
        progress = default_progress_state()
        if prev_progress:
            progress.update(prev_progress)
        progress["loop_flags"] = []
        progress["turns_in_same_mode"] = 0
        return progress

    monkeypatch.setattr(
        "negotiation.negotiation_graph.update_progress_state",
        fake_update_progress_state,
    )

    state = SessionState(user_id="storm", session_id="storm")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    gate_state = state.progress_state["gate_state"]
    gate_state["input_shape_prev"] = input_shape_features("ok")
    gate_state["allowed_ids_hash_prev"] = stable_allowed_ids_hash(["rapport_build"])
    gate_state["precedence_signature_prev"] = precedence_signature(
        {
            "mode": "opening_or_other",
            "reason": "test",
            "min_policy_tags": [],
            "block_policy_tags": [],
            "phase_floor": None,
            "allow_closing": True,
        }
    )

    for idx in range(15):
        message = "ok" if idx % 2 == 0 else "vale"
        run_negotiation_agent(state, message, deps=deps)

    assert planner_calls["count"] <= 2
    belief_refreshes = [
        trace
        for trace in state.debug_trace
        if not trace.get("belief_update_meta", {}).get("belief_update_skipped", True)
    ]
    assert len(belief_refreshes) <= 2
    assert llm_calls["count"] == 0


def test_interaction_propagates_when_world_extractor_skipped(monkeypatch):
    planner_calls = {"count": 0}

    def fake_plan_phase_policy(*_args, **_kwargs):
        planner_calls["count"] += 1
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, default_policy_decision(), {}

    def fake_extract_state_patch_llm(*_args, **_kwargs):
        raise AssertionError("LLM extractor should not be called when world is skipped.")

    deps = _fake_deps(fake_plan_phase_policy)
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "true")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    monkeypatch.setenv("WORLD_REFRESH_INTERVAL_TURNS", "50")
    monkeypatch.setenv("PHASE_POLICY_REFRESH_INTERVAL_TURNS", "50")
    monkeypatch.setattr(
        "negotiation.world_state_updater.extract_state_patch_llm",
        fake_extract_state_patch_llm,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="skip", session_id="skip")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "hola", deps=deps)

    gate_state = state.progress_state["gate_state"]
    gate_state["input_shape_prev"] = input_shape_features("me parece bien")
    gate_state["last_world_refresh_turn"] = state.turn_count

    run_negotiation_agent(state, "me parece bien", deps=deps)

    trace = state.debug_trace[-1]
    assert trace["extractor_used"] is False
    assert trace["gates"]["skip_reasons"]["world"] == "interval_hold"
    interaction_diff = trace["world_diff"]["interaction"]["implicit_acceptance"]
    assert interaction_diff["before"] is False
    assert interaction_diff["after"] is True
    assert planner_calls["count"] >= 2
