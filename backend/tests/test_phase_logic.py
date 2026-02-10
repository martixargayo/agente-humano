from negotiation.phase_state_updater import _apply_hysteresis
from negotiation.policy_planner import _phase_bonus, repair_policy_by_phase


def test_phase_bonus_multi_phase_matches_both():
    phases = ["climate", "interests"]
    assert _phase_bonus(phases, "climate") == 2
    assert _phase_bonus(phases, "interests") == 2


def test_phase_hysteresis_holds_on_low_confidence():
    prev = {
        "phase": "climate",
        "phase_proposed": "",
        "phase_effective": "climate",
        "recovery_mode": False,
        "recovery_stable_turns": 0,
        "confidence": 0.6,
        "reasons": [],
        "last_updated_turn": 1,
    }

    current = prev
    for turn in range(2, 7):
        proposed = {
            "phase": "formalize" if turn % 2 == 0 else "adjust",
            "phase_effective": "formalize" if turn % 2 == 0 else "adjust",
            "confidence": 0.6,
            "reasons": ["world:price_mentioned"],
            "recovery_mode": False,
        }
        current, _ = _apply_hysteresis(current, proposed, turn_count=turn)

    assert current["phase_effective"] == "climate"
    assert current["last_updated_turn"] == 6


def test_repair_policy_by_phase_prefers_bonus_two():
    policy_catalog = {
        "open_policy": ["climate"],
        "close_policy": ["formalize"],
    }
    chosen, meta = repair_policy_by_phase(
        chosen_id="close_policy",
        allowed_ids=["close_policy", "open_policy"],
        policy_catalog=policy_catalog,
        current_phase="climate",
        preferred_ids=["open_policy"],
        commitment_level="soft",
        policy_attempts=None,
    )

    assert meta["phase_repair_used"] is True
    assert meta["phase_repair_from"] == "close_policy"
    assert chosen == "open_policy"
