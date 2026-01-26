import importlib
import os

import pytest

from negotiation.schemas import (
    default_belief_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from negotiation.progress_updater import update_progress_state
from negotiation.validation import (
    normalize_policy_decision,
    normalize_progress_state,
    normalize_world_state,
)


def test_normalize_world_state_missing_tone_non_strict():
    import negotiation.validation as validation

    original = validation._STRICT_NORMALIZATION
    validation._STRICT_NORMALIZATION = False
    try:
        world, issues = normalize_world_state({})
    finally:
        validation._STRICT_NORMALIZATION = original

    assert world == default_world_state()
    assert "tone_signal_missing" in issues


def test_normalize_world_state_invalid_tone_non_strict():
    import negotiation.validation as validation

    original = validation._STRICT_NORMALIZATION
    validation._STRICT_NORMALIZATION = False
    try:
        world, issues = normalize_world_state({"tone_signal": "extra", "price_mentioned": True})
    finally:
        validation._STRICT_NORMALIZATION = original

    assert world["tone_signal"] == "neutral"
    assert world["price_mentioned"] is True
    assert "tone_signal_invalid" in issues


def test_normalize_world_state_missing_tone_strict_returns_defaults():
    import negotiation.validation as validation

    original = validation._STRICT_NORMALIZATION
    validation._STRICT_NORMALIZATION = True
    try:
        world, issues = normalize_world_state({"price_mentioned": True})
    finally:
        validation._STRICT_NORMALIZATION = original

    assert world == default_world_state()
    assert "tone_signal_missing" in issues


def test_normalize_policy_decision_invalid_policy_id_fallback():
    decision, issues = normalize_policy_decision(
        {"policy_id": "nope", "reason": "x", "micro_goal": "y"},
        ["rapport_build"],
    )

    assert decision == default_policy_decision()
    assert "policy_id_invalid" in issues


def test_normalize_progress_state_legacy_fields():
    progress, issues = normalize_progress_state(
        {"last_policy_id": "rapport_build", "last_policy_outcome": "good"}
    )

    assert issues == []
    assert progress["last_executed_policy_id"] == "rapport_build"
    assert progress["last_chosen_policy_id"] == "rapport_build"
    assert progress["last_executed_policy_outcome"] == "good"


def test_update_progress_state_tracks_policy_last_outcome():
    prev_world = default_world_state()
    world = default_world_state()
    prev_belief = default_belief_state()
    prev_belief["dynamics"]["interaction_health"] = "tense"
    belief = default_belief_state()
    belief["dynamics"]["interaction_health"] = "stable"

    last_policy_executed = default_policy_decision()
    last_policy_executed["policy_id"] = "rapport_build"

    progress = update_progress_state(
        None,
        default_policy_decision(),
        last_policy_executed,
        prev_world,
        world,
        prev_belief,
        belief,
    )

    assert progress["last_executed_policy_outcome"] == "good"
    assert progress["policy_last_outcome"].get("rapport_build") == "good"


def test_has_belief_evidence_delta_triggers_on_critical_flag_change():
    from negotiation.belief_state_updater import has_belief_evidence_delta

    prev = default_world_state()
    cur = default_world_state()
    world_diff = {}
    user_message = ""

    cur["deadline_claimed"] = True
    assert has_belief_evidence_delta(world_diff, user_message, prev, cur) is True


def test_has_belief_evidence_delta_triggers_on_tone_change():
    from negotiation.belief_state_updater import has_belief_evidence_delta

    prev = default_world_state()
    cur = default_world_state()

    cur["tone_signal"] = "tense"
    assert has_belief_evidence_delta({}, "", prev, cur) is True


def test_belief_reasons_tiebreak_is_deterministic_with_real_keys():
    from negotiation.belief_state_updater import _BeliefReasonModel, _BeliefStateModel

    reasons = {
        "tone_signal": _BeliefReasonModel(weight=0.5, confidence=0.5, evidence="x"),
        "docs_signal": _BeliefReasonModel(weight=0.5, confidence=0.5, evidence="x"),
    }

    limited = _BeliefStateModel._limit_reasons(reasons)

    assert list(limited.keys()) == ["docs_signal", "tone_signal"]


def test_temporal_invariant_last_policy_executed_is_persisted(monkeypatch):
    from negotiation.negotiation_graph import run_negotiation_agent
    from negotiation.schemas import default_belief_state, default_policy_decision
    from state import SessionState

    def fake_plan_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "rapport_build"
        return decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*args, **kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    class _FakeLLMResult:
        def __init__(self, content: str):
            self.content = content

    class _FakeLLM:
        def invoke(self, messages):
            return _FakeLLMResult("ok-response")

    monkeypatch.setattr(
        "negotiation.negotiation_graph.plan_policy", fake_plan_policy, raising=False
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.update_belief_state",
        fake_update_belief_state,
        raising=False,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_policy_tactics", lambda *args, **kwargs: "", raising=False
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda text, user_message: text,
        raising=False,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.executor_llm", _FakeLLM(), raising=False
    )

    state = SessionState(user_id="u", session_id="s")
    run_negotiation_agent(state, "hola")

    assert state.last_policy_executed is not None
    assert state.last_policy_executed.get("policy_id") == "rapport_build"


def test_allowed_policy_ids_uses_outcome_per_policy():
    os.environ.setdefault("OPENAI_API_KEY", "test")
    from negotiation import policy_planner

    importlib.reload(policy_planner)

    world = default_world_state()
    belief = default_belief_state()
    belief["dynamics"]["interaction_health"] = "stable"
    world["price_mentioned"] = False
    progress = default_progress_state()
    ids = policy_planner.list_policy_ids()
    assert len(ids) >= 2
    p1, p2 = ids[0], ids[1]
    progress["policy_attempts"] = {p1: 3, p2: 3}
    progress["policy_last_outcome"] = {p1: "bad", p2: "good"}

    allowed = policy_planner.allowed_policy_ids(world, belief, progress)

    assert p1 not in allowed
    assert p2 in allowed


def test_normalize_progress_policy_attempts_accepts_numeric_strings():
    progress, issues = normalize_progress_state({"policy_attempts": {"rapport_build": "3"}})

    assert progress["policy_attempts"]["rapport_build"] == 3
    assert not any("policy_attempts_invalid_value" in issue for issue in issues)


def test_normalize_progress_policy_attempts_reports_invalid_values():
    progress, issues = normalize_progress_state({"policy_attempts": {"rapport_build": "abc"}})

    assert "policy_attempts_invalid_value:rapport_build" in issues
    assert "rapport_build" not in progress["policy_attempts"]
