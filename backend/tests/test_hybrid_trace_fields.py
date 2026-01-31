from types import SimpleNamespace

from negotiation.gate_utils import gate_phase_policy
from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import (
    default_belief_state,
    default_intent_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from negotiation.world_state_updater import update_world_state, diff_world_state
from state import SessionState


def _fake_deps(plan_phase_policy):
    def fake_update_belief_state(*_args, **_kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def fake_execute(_messages):
        return "ok"

    return AgentDeps(
        plan_phase_policy=plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )


def test_policy_id_is_clamped_to_allowed_ids(monkeypatch):
    def fake_plan_phase_policy(*_args, **_kwargs):
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        decision = default_policy_decision()
        decision["policy_id"] = "challenge_anchor_indirect"
        return phase_candidate, decision, {}

    deps = _fake_deps(fake_plan_phase_policy)
    monkeypatch.setattr(
        "negotiation.negotiation_graph.allowed_policy_ids",
        lambda *_a, **_k: ["safe_neutral"],
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="u", session_id="s")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "hola", deps=deps)

    trace = state.debug_trace[-1]
    assert trace["policy_decision"]["policy_id"] == "safe_neutral"


def test_phase_repair_reflected_in_trace(monkeypatch):
    def fake_plan_phase_policy(*_args, **_kwargs):
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        decision = default_policy_decision()
        decision["policy_id"] = "info_extract_critical"
        return phase_candidate, decision, {}

    deps = _fake_deps(fake_plan_phase_policy)
    monkeypatch.setattr(
        "negotiation.negotiation_graph.compute_precedence",
        lambda *_a, **_k: SimpleNamespace(
            mode="closing_push",
            reason="test",
            min_policy_tags=set(),
            block_policy_tags=set(),
            phase_floor="closing",
            allow_closing=True,
        ),
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.allowed_policy_ids",
        lambda *_a, **_k: ["info_extract_critical", "close_with_conditions"],
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.repair_policy_by_phase",
        lambda *_a, **_k: ("close_with_conditions", {"phase_repair_used": True}),
    )

    state = SessionState(user_id="u2", session_id="s2")
    world_state = default_world_state()
    world_state["price_mentioned"] = True
    state.world_state = world_state
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "hola", deps=deps)

    trace = state.debug_trace[-1]
    assert trace["phase_candidate"]["phase"] == "opening"
    assert trace["phase_effective"]["phase"] == "closing"
    assert trace["policy_pre_repair"]["policy_id"] == "info_extract_critical"
    assert trace["policy_post_repair"]["policy_id"] != trace["policy_pre_repair"]["policy_id"]


def test_skip_uses_safe_neutral_when_no_last_policy(monkeypatch):
    def fake_plan_phase_policy(*_args, **_kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "rapport_build"
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, decision, {}

    deps = _fake_deps(fake_plan_phase_policy)
    monkeypatch.setattr(
        "negotiation.negotiation_graph.gate_phase_policy",
        lambda **_kwargs: (True, "forced_skip"),
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.allowed_policy_ids",
        lambda *_a, **_k: ["safe_neutral"],
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="u3", session_id="s3")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "hola", deps=deps)

    trace = state.debug_trace[-1]
    assert trace["policy_decision"]["policy_id"] == "safe_neutral"
    assert trace["phase_candidate"] is None


def test_allowed_ids_hash_persisted_and_stable(monkeypatch):
    def fake_plan_phase_policy(*_args, **_kwargs):
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, default_policy_decision(), {}

    deps = _fake_deps(fake_plan_phase_policy)
    monkeypatch.setattr(
        "negotiation.negotiation_graph.allowed_policy_ids",
        lambda *_a, **_k: ["safe_neutral", "rapport_build"],
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="u4", session_id="s4")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "hola", deps=deps)
    first_hash = state.progress_state["gate_state"]["allowed_ids_hash_prev"]

    run_negotiation_agent(state, "otra vez", deps=deps)
    gate_state = state.progress_state["gate_state"]
    assert gate_state["allowed_ids_hash_prev"] == first_hash
    assert gate_state["allowed_ids_hash_stable_count"] == 1


def test_interaction_present_in_debug_trace(monkeypatch):
    def fake_plan_phase_policy(*_args, **_kwargs):
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, default_policy_decision(), {}

    deps = _fake_deps(fake_plan_phase_policy)
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "false")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="ui", session_id="si")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "me parece bien", deps=deps)

    trace = state.debug_trace[-1]
    assert trace["world_new"]["interaction"]["implicit_acceptance"] is True
    assert "interaction" in trace["world_diff"]


def test_gate_phase_policy_triggers_on_interaction_change():
    world_diff = {"interaction": {"implicit_acceptance": {"before": False, "after": True}}}
    planner_skipped, reason = gate_phase_policy(
        world_diff=world_diff,
        precedence_changed=False,
        intent_transition_present=False,
        loop_flags_changed_flag=False,
        allowed_ids_hash_changed=False,
        turn_count=2,
        last_refresh_turn=1,
    )

    assert planner_skipped is False
    assert reason == "strong_signals"


def test_gate_phase_policy_skips_on_repeated_ack(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "false")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    prev_world, _ = update_world_state(default_world_state(), "ok")
    new_world, _ = update_world_state(prev_world, "ok")
    world_diff = diff_world_state(prev_world, new_world)

    planner_skipped, reason = gate_phase_policy(
        world_diff=world_diff,
        precedence_changed=False,
        intent_transition_present=False,
        loop_flags_changed_flag=False,
        allowed_ids_hash_changed=False,
        turn_count=2,
        last_refresh_turn=1,
    )

    assert world_diff == {}
    assert planner_skipped is True
    assert reason == "interval_hold"


def test_planner_refresh_on_implicit_acceptance(monkeypatch):
    called = {"count": 0}

    def fake_plan_phase_policy(*_args, **_kwargs):
        called["count"] += 1
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, default_policy_decision(), {}

    deps = _fake_deps(fake_plan_phase_policy)
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "false")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    monkeypatch.setattr(
        "negotiation.negotiation_graph.allowed_policy_ids",
        lambda *_a, **_k: ["rapport_build"],
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.update_intent_state",
        lambda **_k: (default_intent_state(), {"intent_transition": "none"}, {}),
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.compute_precedence",
        lambda *_a, **_k: SimpleNamespace(
            mode="opening_or_other",
            reason="test",
            min_policy_tags=set(),
            block_policy_tags=set(),
            phase_floor=None,
            allow_closing=True,
        ),
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="u5", session_id="s5")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "hola", deps=deps)
    run_negotiation_agent(state, "me parece bien", deps=deps)

    assert called["count"] >= 2


def test_interaction_does_not_increase_llm_calls(monkeypatch):
    called = {"llm": 0}

    def fake_extract_state_patch_llm(*_args, **_kwargs):
        called["llm"] += 1
        raise AssertionError("LLM extractor should not be called for short ack.")

    monkeypatch.setenv("USE_LLM_EXTRACTOR", "true")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    monkeypatch.setattr(
        "negotiation.world_state_updater.extract_state_patch_llm",
        fake_extract_state_patch_llm,
    )

    world, _meta = update_world_state(default_world_state(), "ok")

    assert called["llm"] == 0
    assert world["interaction"]["implicit_acceptance"] is True
