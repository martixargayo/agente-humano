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
    new_text, violations = validate_and_repair(
        "Puedo pagar 12000 ahora mismo.",
        constraints,
        {"policy_id": "hold_position", "reason": "", "micro_goal": "", "risk_posture": "low", "capabilities": None, "why_short": "", "inputs_used": []},
        {},
    )
    assert violations
    assert "12000" not in new_text
