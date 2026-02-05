from negotiation.validator import validate_and_repair, validate_response


def test_validate_response_flags_violations():
    violations = validate_response("Tengo acceso a tu cuenta para revisarlo.", {})
    assert "claims_internal_access" in violations


def test_validate_and_repair_fallback_on_critical():
    new_text, violations, meta = validate_and_repair(
        "He accedido a tu cuenta y ya lo hice.",
        {},
        {"policy_id": "hold_position", "reason": "", "micro_goal": "", "risk_posture": "low", "capabilities": None, "why_short": "", "inputs_used": []},
        {},
    )
    assert violations
    assert meta["fallback_applied"] is True
    assert new_text != "He accedido a tu cuenta y ya lo hice."


def test_validate_response_ignores_non_price_numbers():
    text = "Tiene 120.000 km, es de 2018 y 150cv."
    violations = validate_response(text, {})
    assert not violations


def test_validate_and_repair_shadow_mode_no_rewrite():
    new_text, violations, meta = validate_and_repair(
        "Podemos hablar de condiciones si quieres.",
        {},
        {"policy_id": "hold_position", "reason": "", "micro_goal": "", "risk_posture": "low", "capabilities": None, "why_short": "", "inputs_used": []},
        {},
    )
    assert not violations
    assert meta["fallback_applied"] is False
    assert new_text == "Podemos hablar de condiciones si quieres."
