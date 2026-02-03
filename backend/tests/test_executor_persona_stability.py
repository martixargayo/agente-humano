from copy import deepcopy
from types import SimpleNamespace

from negotiation.negotiation_graph import executor_node
from negotiation.schemas import default_policy_decision, default_progress_state, default_world_state


def test_executor_persona_stability():
    payload = "{\"response_text\":\"Entendido, ¿qué falta?\",\"asked_question\":true,\"requested_info_slots\":[],\"tone_used\":\"neutral\",\"followup_intent\":null,\"render_meta\":{}}"
    progress = default_progress_state()
    progress["render_state"] = {
        "persona_id": "avatar_sales",
        "scene_id": "default_chat",
        "style_id": "default",
        "language": "es",
    }
    original_progress = deepcopy(progress)
    state = {
        "deps": SimpleNamespace(execute=lambda _messages: payload),
        "long_memory": "",
        "short_memory": "",
        "user_message": "hola",
        "policy_decision": default_policy_decision(),
        "progress_state": progress,
        "constraints_struct": {},
        "world_state": default_world_state(),
    }
    executor_node(state)
    assert state.get("executor_render_meta", {}).get("persona_id") == "avatar_sales"
    assert state.get("progress_state") == original_progress
