from types import SimpleNamespace

from negotiation.negotiation_graph import executor_node
from negotiation.schemas import default_policy_decision, default_progress_state, default_world_state


def test_executor_backcompat_text():
    payload = "{\"response_text\":\"Vale, ¿qué necesitas?\",\"asked_question\":true,\"requested_info_slots\":[],\"tone_used\":\"neutral\",\"followup_intent\":null,\"render_meta\":{}}"
    state = {
        "deps": SimpleNamespace(execute=lambda _messages: payload),
        "long_memory": "",
        "short_memory": "",
        "user_message": "hola",
        "policy_decision": default_policy_decision(),
        "progress_state": default_progress_state(),
        "constraints_struct": {},
        "world_state": default_world_state(),
    }
    executor_node(state)
    assert state.get("assistant_message") == state.get("executor_output").get("response_text")
