from copy import deepcopy
from types import SimpleNamespace

from negotiation.negotiation_graph import executor_node
from negotiation.schemas import default_policy_decision, default_progress_state, default_world_state


def test_executor_persona_stability():
    payload = "{\"response_text\":\"Entendido, ¿qué falta?\",\"asked_question\":true,\"requested_info_slots\":[],\"tone_used\":\"neutral\",\"followup_intent\":null,\"render_meta\":{}}"
    progress = default_progress_state()
    progress["persona_profile"] = {
        "persona_id": "daniel_buyer",
        "role": "comprador humano",
        "voice_register": "neutral",
        "base_language": "es",
        "values": ["calm"],
        "hard_limits": ["no_internal_access"],
        "do": ["be direct"],
        "dont": ["sound like ai"],
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
    assert state.get("executor_render_meta", {}).get("persona_id") == "daniel_buyer"
    assert state.get("progress_state") == original_progress
