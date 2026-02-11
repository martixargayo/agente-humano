from negotiation.response_validator import validate_and_repair, validate_response


def test_validate_response_flags_violations():
    constraints = {"avoid_reveal_own_numbers": True, "respect_batna": True, "max_total_cost": 10000}
    violations = validate_response("Puedo pagar 12000 ahora mismo.", constraints)
    assert "reveal_own_numbers" in violations
    assert "exceed_max_total_cost" in violations


def test_validate_and_repair_uses_llm(monkeypatch):
    class FakeLLM:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, _messages):
            class Result:
                content = "No puedo pasarme de mi límite, ¿podemos ajustar condiciones?"

            return Result()

    monkeypatch.setattr("negotiation.response_validator.ChatOpenAI", FakeLLM)
    constraints = {"avoid_reveal_own_numbers": True, "respect_batna": True, "max_total_cost": 10000}
    new_text, violations, meta = validate_and_repair(
        "Puedo pagar 12000 ahora mismo.",
        constraints,
        {"policy_id": "hold_position", "reason": "", "micro_goal": "", "risk_posture": "low", "capabilities": None, "why_short": "", "inputs_used": []},
        {},
    )
    assert violations
    assert meta["repaired_used"] is True
    assert "12000" not in new_text


def test_validate_response_ignores_non_price_numbers():
    constraints = {"avoid_reveal_own_numbers": True, "respect_batna": True, "max_total_cost": 10000}
    text = "Tiene 120.000 km, es de 2018 y 150cv."
    violations = validate_response(text, constraints)
    assert "exceed_max_total_cost" not in violations


def test_validate_and_repair_fallback_when_still_violating(monkeypatch):
    class FakeLLM:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, _messages):
            class Result:
                content = "Puedo pagar 15000 ahora mismo."

            return Result()

    monkeypatch.setattr("negotiation.response_validator.ChatOpenAI", FakeLLM)
    constraints = {"avoid_reveal_own_numbers": True, "respect_batna": True, "max_total_cost": 10000}
    new_text, violations, _meta = validate_and_repair(
        "Puedo pagar 12000 ahora mismo.",
        constraints,
        {"policy_id": "hold_position", "reason": "", "micro_goal": "", "risk_posture": "low", "capabilities": None, "why_short": "", "inputs_used": []},
        {},
    )
    assert violations
    assert "Prefiero no comprometer cifras ahora" in new_text
