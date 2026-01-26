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


def test_allowed_policy_ids_uses_outcome_per_policy():
    os.environ.setdefault("OPENAI_API_KEY", "test")
    from negotiation import policy_planner

    importlib.reload(policy_planner)

    world = default_world_state()
    belief = default_belief_state()
    progress = default_progress_state()
    progress["policy_attempts"] = {"rapport_build": 3, "test_credibility": 3}
    progress["policy_last_outcome"] = {"rapport_build": "bad", "test_credibility": "good"}

    allowed = policy_planner.allowed_policy_ids(world, belief, progress)

    assert "rapport_build" not in allowed
    assert "test_credibility" in allowed
