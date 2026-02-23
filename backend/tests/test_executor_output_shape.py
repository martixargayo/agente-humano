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


def test_executor_prompt_includes_instruction_when_present(monkeypatch):
    captured = {"prompt": ""}

    def _execute(messages):
        captured["prompt"] = messages[1].content
        return (
            '{"response_text":"Ok","asked_question":false,'
            '"requested_info_slots":[],"tone_used":"neutral",'
            '"followup_intent":null,"render_meta":{}}'
        )

    state = {
        "deps": SimpleNamespace(execute=_execute),
        "long_memory": "",
        "short_memory": "",
        "user_message": "hola",
        "policy_decision": default_policy_decision(),
        "progress_state": default_progress_state(),
        "world_state": default_world_state(),
        "executor_instruction": {
            "schema_version": "v1",
            "plan_id": "plan_t1",
            "step_idx": 0,
            "instruction": "Pide dato verificable",
            "safe_mode": "normal",
        },
    }
    executor_node(state)
    assert "B) INSTRUCCION_DEL_PLANNER (PRIORIDAD MAXIMA)" in captured["prompt"]
    assert '"plan_id": "plan_t1"' in captured["prompt"]
    assert "PERSONA PROFILE (fixed):" not in captured["prompt"]
    assert "SCENE PROFILE (fixed):" not in captured["prompt"]


def test_executor_prompt_uses_render_state_profiles():
    captured = {"prompt": ""}

    def _execute(messages):
        captured["prompt"] = messages[1].content
        return (
            '{"response_text":"Ok","asked_question":false,'
            '"requested_info_slots":[],"tone_used":"neutral",'
            '"followup_intent":null,"render_meta":{}}'
        )

    progress = default_progress_state()
    progress["render_state"] = {
        "persona_id": "buyer_mustang67_v1",
        "scene_id": "mustang67_in_person_viewing",
        "style_id": "psyplay_compact",
    }
    progress["speaker_of_user_message"] = "seller"

    state = {
        "deps": SimpleNamespace(execute=_execute),
        "long_memory": "",
        "short_memory": "",
        "user_message": "¿qué me ofreces?",
        "policy_decision": default_policy_decision(),
        "progress_state": progress,
        "world_state": default_world_state(),
    }

    executor_node(state)
    assert '"persona_id": "buyer_mustang67_v1"' in captured["prompt"]
    assert '"scene_id": "mustang67_in_person_viewing"' in captured["prompt"]
    assert "D) MENSAJE_ACTUAL (DEL HABLANTE)" in captured["prompt"]
    assert "SPEAKER_OF_USER_MESSAGE: seller" in captured["prompt"]
