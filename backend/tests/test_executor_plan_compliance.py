from types import SimpleNamespace

from negotiation.negotiation_graph import executor_node
from negotiation.schemas import default_policy_decision, default_progress_state, default_world_state


def _state_with_response(payload: str) -> dict:
    progress = default_progress_state()
    return {
        "deps": SimpleNamespace(execute=lambda _messages: payload),
        "long_memory": "",
        "short_memory": "",
        "user_message": "hola",
        "policy_decision": default_policy_decision(),
        "progress_state": progress,
        "world_state": default_world_state(),
    }


def test_executor_autorepairs_missing_question_for_question_instruction():
    payload = (
        '{"response_text":"Entiendo tu punto y podemos avanzar",'
        '"asked_question":false,"requested_info_slots":[],"tone_used":"neutral",'
        '"followup_intent":null,"render_meta":{}}'
    )
    state = _state_with_response(payload)
    state["executor_instruction"] = {
        "instruction": "Pregunta por los términos concretos",
        "safe_mode": "normal",
        "ask": [],
    }

    executor_node(state)

    assert state["assistant_message"].endswith("?")
    meta = state["executor_validator_meta"]
    assert meta["executor_followed_instruction"] is True
    assert "instruction_autorepair_question" in meta.get("instruction_enforcement", [])


def test_executor_enforces_disallow_numbers_constraint():
    payload = (
        '{"response_text":"Puedo pagar 200 euros hoy",'
        '"asked_question":false,"requested_info_slots":[],"tone_used":"neutral",'
        '"followup_intent":null,"render_meta":{}}'
    )
    state = _state_with_response(payload)
    state["progress_state"]["render_constraints_struct"] = {
        "disallow_numbers": True,
        "max_questions": 2,
    }

    executor_node(state)

    assert not any(ch.isdigit() for ch in state["assistant_message"])
    meta = state["executor_validator_meta"]
    assert "constraints:disallow_numbers" in meta.get("constraints_enforcement", [])


def test_executor_allows_human_first_with_bridge_and_step_ask():
    payload = (
        '{"response_text":"Todo bien, gracias por preguntar. Vale, volviendo al coche, ¿qué kilometraje exacto tiene?",'
        '"asked_question":true,"requested_info_slots":["kilometraje"],"tone_used":"neutral",'
        '"followup_intent":null,"render_meta":{}}'
    )
    state = _state_with_response(payload)
    state["executor_instruction"] = {
        "instruction": "Responde breve y pregunta kilometraje",
        "safe_mode": "normal",
        "ask": ["¿qué kilometraje exacto tiene?"],
    }
    state["advisor_recs"] = {
        "human_mode": "answer_then_bridge",
        "answer_focus": "Todo bien, gracias por preguntar.",
        "bridge": "Vale, volviendo al coche,",
    }

    executor_node(state)

    meta = state["executor_validator_meta"]
    assert meta["executor_followed_instruction"] is True
    assert meta.get("deviation_reason", "") == ""
    assert "missing_required_ask_slot" not in (meta.get("instruction_enforcement") or [])
