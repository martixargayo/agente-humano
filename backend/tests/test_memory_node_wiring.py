from __future__ import annotations

import json

from negociacion.nodes.memory_node import MemoryOutput
from negociacion.orchestration.flow_config import (
    _call_structured,
    _memory_fallback,
    _build_user_turn,
    apply_memory_output_to_state,
    build_memory_input,
    build_memory_messages,
)
from negociacion.state.canonical_state import MemoryEpisodicItem, build_default_canonical_state
from negociacion.state.shared_types import StructuredCallSource, ThreadMode


def _build_state():
    state = build_default_canonical_state(session_id="s1", thread_mode=ThreadMode.conversation)
    state.memory_working.current_topic = "precio"
    state.memory_working.pending_question = "¿puedes confirmar presupuesto?"
    state.memory_working.last_turn_summary = "se pidió confirmar el presupuesto"
    state.memory_episodic = [
        MemoryEpisodicItem(event_type="important_fact", event_summary="presupuesto máximo de 1000", turn_id="1")
    ]
    return state


def test_build_memory_input_exact_fields_and_sources():
    state = _build_state()
    user_turn = _build_user_turn("Hola, mi tope es 1000", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "2",
        "prompt_version": "memory_v3",
        "schema_version": "memory_input.v1",
        "model_target": "gpt-5-nano",
    }
    recent = [
        {"role": "user", "text": "hola"},
        {"role": "assistant", "text": "¿qué presupuesto tienes?"},
    ]

    payload = build_memory_input(state, recent, user_turn, trace_meta)  # type: ignore[arg-type]
    dumped = payload.model_dump(mode="json")

    assert set(dumped.keys()) == {
        "schema_version",
        "task_contract",
        "user_turn",
        "recent_dialogue_short",
        "memory_working_current",
        "recent_memory_episodic_short",
        "trace_meta",
    }
    assert dumped["schema_version"] == "memory_input.v1"
    assert dumped["memory_working_current"] == state.memory_working.model_dump(mode="json")
    assert dumped["recent_memory_episodic_short"] == [x.model_dump(mode="json") for x in state.memory_episodic]
    assert dumped["task_contract"]["node_name"] == "memory"
    assert dumped["task_contract"]["output_schema_version"] == "memory.v1"


def test_memory_output_schema_contract_and_message_payload():
    output = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [
                {"event_type": "offer", "event_summary": "ofrece 2 cuotas", "turn_id": "2"}
            ],
            "working_memory_new": {
                "current_topic": "forma de pago",
                "pending_question": None,
                "last_turn_summary": "usuario ofreció pagar en 2 cuotas",
            },
        }
    )
    assert output.schema_version == "memory.v1"

    state = _build_state()
    user_turn = _build_user_turn("texto", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "2",
        "prompt_version": "memory_v3",
        "schema_version": "memory_input.v1",
        "model_target": "gpt-5-nano",
    }
    msg = build_memory_messages("PROMPT", build_memory_input(state, [], user_turn, trace_meta))  # type: ignore[arg-type]
    assert msg[0]["role"] == "developer"
    assert "<memory_input_json>" in msg[1]["content"]


def test_apply_memory_output_to_state_append_and_refresh():
    state = _build_state()
    output = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [
                {"event_type": "commitment", "event_summary": "acepta responder mañana", "turn_id": "2"}
            ],
            "working_memory_new": {
                "current_topic": "seguimiento",
                "pending_question": "¿confirmas fecha?",
                "last_turn_summary": "aceptó responder mañana",
            },
        }
    )

    apply_memory_output_to_state(state, output)

    assert state.memory_episodic[-1].event_summary == "acepta responder mañana"
    assert state.memory_working.current_topic == "seguimiento"
    assert state.memory_working.pending_question == "¿confirmas fecha?"
    assert state.memory_working.last_turn_summary == "aceptó responder mañana"


def test_memory_fallback_keeps_state_and_returns_valid_output():
    state = _build_state()
    fallback = _memory_fallback(state, "2")

    assert fallback.episodic_append == []
    assert fallback.working_memory_new.current_topic == state.memory_working.current_topic
    assert fallback.working_memory_new.pending_question == state.memory_working.pending_question
    assert fallback.schema_version == "memory.v1"


class _FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.refusal = None


class _FakeResponsesAPI:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _FakeResponse(
            json.dumps(
                {
                    "schema_version": "memory.v1",
                    "episodic_append": [],
                    "working_memory_new": {
                        "current_topic": None,
                        "pending_question": None,
                        "last_turn_summary": "ok",
                    },
                }
            )
        )


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponsesAPI()


def test_call_structured_uses_strict_json_schema_and_validates():
    client = _FakeClient()
    result = _call_structured(
        client=client,
        model="gpt-5-nano",
        messages=[{"role": "developer", "content": "x"}],
        response_model=MemoryOutput,
        reasoning_effort="low",
        request_context={},
        store=False,
    )

    assert result.source == StructuredCallSource.model
    assert client.responses.kwargs["text"]["format"]["type"] == "json_schema"
    assert client.responses.kwargs["text"]["format"]["strict"] is True
