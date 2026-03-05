import json

from negotiation.nodes.executor_node import executor_node
from negotiation.schemas import default_progress_state


class _Raw:
    def __init__(self, content: str):
        self.content = content


class _FinalizerDummy:
    def __init__(self):
        self.last_messages = None

    def invoke(self, messages):
        self.last_messages = messages
        return _Raw(
            json.dumps(
                {
                    "schema_version": "executor_v2",
                    "response_text": "Perfecto.",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "calido_profesional",
                    "followup_intent": None,
                    "render_meta": {},
                },
                ensure_ascii=False,
            )
        )


def _base_state():
    return {
        "user_message": "hola",
        "last_seller_utterance": "",
        "planner_semantic_output": {"phase": "clima_humano", "next_move_hint": "TACTIC: frame"},
        "progress_state": default_progress_state(),
        "turn_count": 1,
    }


def test_finalizer_uses_user_message_as_fallback_for_empty_last_seller(monkeypatch, caplog):
    finalizer = _FinalizerDummy()
    monkeypatch.setenv("NEGOTIATION_EXECUTOR_FINALIZER_ENABLED", "1")
    monkeypatch.setattr(
        "negotiation.nodes.executor_node.render_executor_output",
        lambda *args, **kwargs: {
            "schema_version": "executor_v2",
            "response_text": "Perfecto.",
            "asked_question": False,
            "requested_info_slots": [],
            "tone_used": "neutral",
            "followup_intent": None,
            "render_meta": {},
        },
    )
    monkeypatch.setattr("negotiation.nodes.executor_node.get_executor_finalizer_llm", lambda: finalizer)

    out = executor_node(_base_state())

    finalizer_prompt = str(finalizer.last_messages[1].content)
    assert "last_seller_utterance: hola" in finalizer_prompt
    assert "user_message: hola" in finalizer_prompt
    assert out["executor_output"]["render_meta"]["finalizer_last_seller_fallback_used"] is True
    assert "finalizer_wiring: last_seller_utterance vacío; usando user_message como fallback" in caplog.text


def test_finalizer_keeps_non_empty_last_seller_without_fallback(monkeypatch):
    finalizer = _FinalizerDummy()
    monkeypatch.setenv("NEGOTIATION_EXECUTOR_FINALIZER_ENABLED", "1")
    monkeypatch.setattr(
        "negotiation.nodes.executor_node.render_executor_output",
        lambda *args, **kwargs: {
            "schema_version": "executor_v2",
            "response_text": "Perfecto.",
            "asked_question": False,
            "requested_info_slots": [],
            "tone_used": "neutral",
            "followup_intent": None,
            "render_meta": {},
        },
    )
    monkeypatch.setattr("negotiation.nodes.executor_node.get_executor_finalizer_llm", lambda: finalizer)

    state = _base_state()
    state["last_seller_utterance"] = "texto vendedor"
    out = executor_node(state)

    finalizer_prompt = str(finalizer.last_messages[1].content)
    assert "last_seller_utterance: texto vendedor" in finalizer_prompt
    assert out["executor_output"]["render_meta"]["finalizer_last_seller_fallback_used"] is False
