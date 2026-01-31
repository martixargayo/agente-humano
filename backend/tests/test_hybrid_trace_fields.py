from types import SimpleNamespace

from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_policy_decision, default_progress_state
from negotiation.schemas import default_world_state
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
