from types import SimpleNamespace

from negotiation.executor import normalize_executor_output
from negotiation.negotiation_graph import executor_node
from negotiation.schemas import default_policy_decision, default_progress_state, default_world_state


def _fake_deps(payload: str):
    return SimpleNamespace(execute=lambda _messages: payload)


def test_executor_output_shape():
    payload = (
        "{\"response_text\":\"Hola, ¿qué necesitas?\","
        "\"asked_question\":true,"
        "\"requested_info_slots\":[\"price\",\"docs\",\"deadline\",\"batna\",\"offer\",\"timing\",\"extra\"],"
        "\"tone_used\":\"friendly\","
        "\"followup_intent\":null,"
        "\"render_meta\":{}}"
    )
    state = {
        "deps": _fake_deps(payload),
        "long_memory": "",
        "short_memory": "",
        "user_message": "hola",
        "policy_decision": default_policy_decision(),
        "progress_state": default_progress_state(),
        "constraints_struct": {},
        "world_state": default_world_state(),
    }
    executor_node(state)
    output = state.get("executor_output")
    assert output
    assert isinstance(output.get("response_text"), str)
    assert output.get("response_text")
    assert output.get("tone_used") in {"friendly", "neutral", "tense"}
    assert len(output.get("requested_info_slots", [])) <= 6


def test_executor_output_normalization_handles_invalid():
    output = normalize_executor_output({"response_text": "", "tone_used": "unknown"})
    assert output["response_text"]
    assert output["tone_used"] == "neutral"
