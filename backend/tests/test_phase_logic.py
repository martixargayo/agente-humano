from negotiation.phase_state_updater import _apply_hysteresis, update_phase_state
from negotiation.policy_planner import _phase_bonus, repair_policy_by_phase
from negotiation.schemas import (
    default_belief_state,
    default_intent_state,
    default_progress_state,
    default_world_state,
)


def test_phase_bonus_multi_phase_matches_both():
    phases = ["opening", "discovery"]
    assert _phase_bonus(phases, "opening") == 2
    assert _phase_bonus(phases, "discovery") == 2


def test_phase_bonus_recovery_override_soft():
    assert _phase_bonus(["recovery"], "recovery") == 3
    assert _phase_bonus(["opening"], "recovery") == 0


def test_phase_hysteresis_holds_on_low_confidence():
    prev = {
        "phase": "opening",
        "confidence": 0.6,
        "reasons": [],
        "last_updated_turn": 1,
    }

    current = prev
    for turn in range(2, 7):
        proposed = {
            "phase": "closing" if turn % 2 == 0 else "bargaining",
            "confidence": 0.6,
            "reasons": ["world:price_mentioned"],
        }
        current, _ = _apply_hysteresis(current, proposed, turn_count=turn)

    assert current["phase"] == "opening"
    assert current["last_updated_turn"] == 6


def test_phase_hard_override_price_firm():
    prev = default_progress_state()["phase_state"]
    world = default_world_state()
    world["price_firm"] = True
    phase, meta = update_phase_state(
        prev_phase_state=prev,
        world_state=world,
        world_diff={"price_firm": {"before": False, "after": True}},
        belief_state=default_belief_state(),
        intent_state=default_intent_state(),
        recent_history_text="",
        turn_count=3,
        precedence=None,
    )

    assert phase["phase"] == "closing"
    assert meta["phase_hard_override_used"] is True


def test_phase_budget_gate_skips_without_signals():
    prev = default_progress_state()["phase_state"]
    prev["last_updated_turn"] = 2
    phase, meta = update_phase_state(
        prev_phase_state=prev,
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        intent_state=None,
        recent_history_text="",
        turn_count=3,
        precedence=None,
    )

    assert phase["phase"] == prev["phase"]
    assert meta["phase_update_reason"] == "budget_hold"


def test_repair_policy_by_phase_prefers_bonus_two():
    policy_catalog = {
        "open_policy": ["opening"],
        "close_policy": ["closing"],
    }
    chosen, meta = repair_policy_by_phase(
        chosen_id="close_policy",
        allowed_ids=["close_policy", "open_policy"],
        policy_catalog=policy_catalog,
        current_phase="opening",
        preferred_ids=["open_policy"],
        commitment_level="soft",
        policy_attempts=None,
    )

    assert meta["phase_repair_used"] is True
    assert meta["phase_repair_from"] == "close_policy"
    assert chosen == "open_policy"


def test_repair_policy_by_phase_skips_on_hard_commitment():
    policy_catalog = {
        "open_policy": ["opening"],
        "close_policy": ["closing"],
    }
    chosen, meta = repair_policy_by_phase(
        chosen_id="close_policy",
        allowed_ids=["close_policy", "open_policy"],
        policy_catalog=policy_catalog,
        current_phase="opening",
        preferred_ids=["open_policy"],
        commitment_level="hard",
        policy_attempts=None,
    )

    assert meta["phase_repair_used"] is False
    assert meta["phase_repair_mode"] == "disabled_intent_hard"
    assert chosen == "close_policy"


def test_repair_policy_by_phase_pref_no_intersection():
    policy_catalog = {
        "open_policy": ["opening"],
        "close_policy": ["closing"],
    }
    chosen, meta = repair_policy_by_phase(
        chosen_id="close_policy",
        allowed_ids=["close_policy", "open_policy"],
        policy_catalog=policy_catalog,
        current_phase="opening",
        preferred_ids=["missing_policy"],
        commitment_level="soft",
        policy_attempts=None,
    )

    assert meta["phase_repair_used"] is False
    assert meta["phase_repair_mode"] == "preferred_no_intersection"
    assert chosen == "close_policy"


def test_repair_policy_by_phase_respects_attempt_budget():
    policy_catalog = {
        "open_policy": ["opening"],
        "close_policy": ["closing"],
    }
    chosen, meta = repair_policy_by_phase(
        chosen_id="close_policy",
        allowed_ids=["close_policy", "open_policy"],
        policy_catalog=policy_catalog,
        current_phase="opening",
        preferred_ids=["open_policy"],
        commitment_level="soft",
        policy_attempts={"open_policy": 3},
    )

    assert meta["phase_repair_used"] is False
    assert chosen == "close_policy"
