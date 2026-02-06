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


os.environ.setdefault("OPENAI_API_KEY", "test")


def test_normalize_world_state_missing_tone_non_strict():
    import negotiation.validation as validation

    original = validation._STRICT_NORMALIZATION
    validation._STRICT_NORMALIZATION = False
    try:
        world, issues = normalize_world_state({})
    finally:
        validation._STRICT_NORMALIZATION = original

    assert world == default_world_state()
    assert issues == []


def test_normalize_world_state_invalid_tone_non_strict():
    import negotiation.validation as validation

    original = validation._STRICT_NORMALIZATION
    validation._STRICT_NORMALIZATION = False
    try:
        world, issues = normalize_world_state(
            {"universal_domain": {"tone_signal": "extra"}, "price_mentioned": True}
        )
    finally:
        validation._STRICT_NORMALIZATION = original

    assert world["universal_domain"]["tone_signal"] == "neutral"
    assert world["negotiation"]["price_mentioned"] is True
    assert "tone_signal_invalid" in issues


def test_normalize_world_state_missing_tone_strict_returns_defaults():
    import negotiation.validation as validation

    original = validation._STRICT_NORMALIZATION
    validation._STRICT_NORMALIZATION = True
    try:
        world, issues = normalize_world_state({"price_mentioned": True})
    finally:
        validation._STRICT_NORMALIZATION = original

    assert world["negotiation"]["price_mentioned"] is True
    assert issues == []


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
    prev_belief["universal"]["dynamics"]["interaction_health"] = "tense"
    belief = default_belief_state()
    belief["universal"]["dynamics"]["interaction_health"] = "stable"

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

    cur["negotiation"]["deadline_claimed"] = True
    assert has_belief_evidence_delta(world_diff, prev, cur) is True


def test_has_belief_evidence_delta_triggers_on_tone_change():
    from negotiation.belief_state_updater import has_belief_evidence_delta

    prev = default_world_state()
    cur = default_world_state()

    cur["universal_domain"]["tone_signal"] = "tense"
    assert has_belief_evidence_delta({}, prev, cur) is True


def test_has_belief_evidence_delta_does_not_use_user_text():
    from negotiation.belief_state_updater import has_belief_evidence_delta

    prev = default_world_state()
    cur = default_world_state()
    extractor_meta = {"decisions": {"should_update_beliefs": False}}

    assert has_belief_evidence_delta({}, prev, cur, extractor_meta) is False


def test_has_belief_evidence_delta_respects_decision_flag():
    from negotiation.belief_state_updater import has_belief_evidence_delta

    prev = default_world_state()
    cur = default_world_state()
    extractor_meta = {"decisions": {"should_update_beliefs": True}}

    assert has_belief_evidence_delta({}, prev, cur, extractor_meta) is True


def test_belief_reasons_tiebreak_is_deterministic_with_real_keys():
    from negotiation.belief_state_updater import _limit_reasons

    reasons = {
        "tone_signal": {"weight": 0.5, "confidence": 0.5, "evidence": "x"},
        "docs_signal": {"weight": 0.5, "confidence": 0.5, "evidence": "x"},
    }

    limited = _limit_reasons(reasons)

    assert list(limited.keys()) == ["docs_signal", "tone_signal"]


def test_belief_reasons_limit_to_top_six():
    from negotiation.belief_state_updater import _limit_reasons

    reasons = {
        "price_signal": {"weight": 0.9, "confidence": 0.9, "evidence": "x"},
        "deadline_signal": {"weight": 0.8, "confidence": 0.8, "evidence": "x"},
        "other_buyer_signal": {"weight": 0.7, "confidence": 0.7, "evidence": "x"},
        "concession_signal": {"weight": 0.6, "confidence": 0.6, "evidence": "x"},
        "docs_signal": {"weight": 0.5, "confidence": 0.5, "evidence": "x"},
        "tone_signal": {"weight": 0.4, "confidence": 0.4, "evidence": "x"},
        "extra_signal": {"weight": 0.3, "confidence": 0.3, "evidence": "x"},
    }

    limited = _limit_reasons(reasons)

    assert len(limited) == 6
    assert "extra_signal" not in limited


def test_temporal_invariant_last_policy_executed_is_persisted(monkeypatch):
    from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
    from negotiation.schemas import default_belief_state, default_policy_decision
    from state import SessionState

    def fake_plan_phase_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "rapport_build"
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*args, **kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def fake_execute(*args, **kwargs) -> str:
        return "ok-response"

    deps = AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )

    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    state = SessionState(user_id="u", session_id="s")
    run_negotiation_agent(state, "hola", deps=deps)

    assert state.last_policy_executed is not None
    assert state.last_policy_executed.get("policy_id") == "rapport_build"


def test_allowed_policy_ids_ignores_outcomes_when_minimal():
    os.environ.setdefault("OPENAI_API_KEY", "test")
    from negotiation import policy_planner

    importlib.reload(policy_planner)

    world = default_world_state()
    belief = default_belief_state()
    progress = default_progress_state()
    progress["policy_attempts"] = {"safe_neutral": 3}
    progress["policy_last_outcome"] = {"safe_neutral": "bad"}

    allowed = policy_planner.allowed_policy_ids(world, belief, progress)

    assert "safe_neutral" in allowed


def test_normalize_progress_policy_attempts_accepts_numeric_strings():
    progress, issues = normalize_progress_state({"policy_attempts": {"rapport_build": "3"}})

    assert progress["policy_attempts"]["rapport_build"] == 3
    assert not any("policy_attempts_invalid_value" in issue for issue in issues)


def test_normalize_progress_policy_attempts_reports_invalid_values():
    progress, issues = normalize_progress_state({"policy_attempts": {"rapport_build": "abc"}})

    assert "policy_attempts_invalid_value:rapport_build" in issues
    assert "rapport_build" not in progress["policy_attempts"]


def test_normalize_progress_phase_state_clamps_and_dedupes():
    progress, issues = normalize_progress_state(
        {
            "phase_state": {
                "phase": "invalid",
                "confidence": 2.5,
                "reasons": ["a", "a", "b"],
                "last_updated_turn": -3,
            }
        }
    )

    assert "phase_invalid" in issues
    assert progress["phase_state"]["phase"] == "opening"
    assert progress["phase_state"]["confidence"] == 1.0
    assert progress["phase_state"]["reasons"] == ["a", "b"]
    assert progress["phase_state"]["last_updated_turn"] == 0
