from negotiation.belief_state_updater import _apply_phase_hysteresis
from negotiation.policy_planner import _phase_bonus, repair_policy_by_phase


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
    proposed = {"phase": "bargaining", "confidence": 0.6, "reasons": ["tone tense"]}

    updated = _apply_phase_hysteresis(prev, proposed, turn_count=3)

    assert updated["phase"] == "opening"
    assert updated["reasons"][0] == "hysteresis_hold"
    assert updated["last_updated_turn"] == 3


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
    )

    assert meta["phase_repair_used"] is True
    assert meta["phase_repair_from"] == "close_policy"
    assert chosen == "open_policy"
