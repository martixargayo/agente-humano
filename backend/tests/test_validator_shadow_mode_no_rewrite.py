from negotiation.validator import validate_and_repair


def test_validator_shadow_mode_no_rewrite():
    text = "Podemos revisarlo y ver opciones."
    new_text, violations, meta = validate_and_repair(
        text,
        {},
        {"policy_id": "safe_neutral", "reason": "", "micro_goal": "", "risk_posture": "low", "capabilities": None, "why_short": "", "inputs_used": []},
        {},
    )
    assert new_text == text
    assert not violations
    assert meta["fallback_applied"] is False
