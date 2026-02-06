from types import SimpleNamespace

from negotiation.gate_utils import gate_phase_policy
from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import (
    default_belief_state,
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
        return (
            '{"schema_version":"world_extractor_v3","universal_domain_patch":{},'
            '"negotiation_domain_patch":{},"universal_patch":{},"open_claims":[]}'
        )

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
        "negotiation.nodes.planner_node.list_policy_ids",
        lambda: ["safe_neutral"],
    )
    monkeypatch.setattr(
        "negotiation.nodes.planner_node.policy_phase_catalog",
        lambda: {"safe_neutral": ["opening"]},
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
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.nodes.planner_node.list_policy_ids",
        lambda: ["info_extract_critical", "close_with_conditions"],
    )
    monkeypatch.setattr(
        "negotiation.nodes.planner_node.policy_phase_catalog",
        lambda: {
            "info_extract_critical": ["opening"],
            "close_with_conditions": ["opening"],
        },
    )
    monkeypatch.setattr(
        "negotiation.nodes.planner_node.repair_policy_by_phase",
        lambda *_a, **_k: ("close_with_conditions", {"phase_repair_used": True}),
    )

    state = SessionState(user_id="u2", session_id="s2")
    world_state = default_world_state()
    world_state["negotiation"]["price_mentioned"] = True
    state.world_state = world_state
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "hola", deps=deps)

    trace = state.debug_trace[-1]
    assert trace["phase_candidate"]["phase"] == "opening"
    assert trace["phase_effective"]["phase"] == "opening"
    assert trace["policy_pre_repair"]["policy_id"] == "info_extract_critical"
    assert trace["policy_post_repair"]["policy_id"] != trace["policy_pre_repair"]["policy_id"]


def test_gate_phase_policy_skips_on_repeated_ack(monkeypatch):
    deps = SimpleNamespace(
        execute=lambda _messages: (
            '{"schema_version":"world_extractor_v3","universal_domain_patch":{},'
            '"negotiation_domain_patch":{},"universal_patch":{},"open_claims":[]}'
        )
    )
    prev_world, _ = update_world_state(default_world_state(), "ok", deps=deps)
    new_world, _ = update_world_state(prev_world, "ok", deps=deps)
    world_diff = diff_world_state(prev_world, new_world)

    planner_skipped, reason, _meta = gate_phase_policy(
        world_diff=world_diff,
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
    monkeypatch.setattr(
        "negotiation.nodes.planner_node.list_policy_ids",
        lambda: ["rapport_build"],
    )
    monkeypatch.setattr(
        "negotiation.nodes.planner_node.policy_phase_catalog",
        lambda: {"rapport_build": ["opening"]},
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="u5", session_id="s5")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "hola", deps=deps)

    assert called["count"] >= 1
