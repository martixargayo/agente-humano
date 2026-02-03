from negotiation.validator import validate_and_repair


def test_validator_critical_fallback():
    text = "He accedido a tu cuenta y ya está resuelto."
    new_text, violations, meta = validate_and_repair(
        text,
        {},
        {"policy_id": "safe_neutral", "reason": "", "micro_goal": "", "risk_posture": "low", "capabilities": None, "why_short": "", "inputs_used": []},
        {},
    )
    assert new_text != text
    assert violations
    assert meta["fallback_applied"] is True
