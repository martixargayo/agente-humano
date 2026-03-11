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
    build_planner_input,
)
from negociacion.state.canonical_state import MemoryEpisodicItem, build_default_canonical_state
from negociacion.state.shared_types import NegotiationPhase, StructuredCallSource, ThreadMode


def _build_state():
    state = build_default_canonical_state(session_id="s1", thread_mode=ThreadMode.conversation)
    state.memory_working.current_topic = "precio"
    state.memory_working.pending_question = "¿puedes confirmar presupuesto?"
    state.memory_working.last_turn_summary = "se pidió confirmar el presupuesto"
    state.memory_episodic = [
        MemoryEpisodicItem(event_type="important_fact", event_summary="presupuesto máximo de 1000", turn_id="1")
    ]
    return state


def _negotiation_base() -> dict[str, object]:
    return {
        "status": "active",
        "active_axes": ["price"],
        "last_offer_self": None,
        "last_offer_other": None,
        "tentative_agreement": None,
        "stall_state": {
            "is_hard_stalemate": False,
            "stalemate_reason": None,
            "self_ultimatum_active": False,
            "self_ultimatum_summary": None,
        },
        "blockers": [],
        "next_open_loop": "cerrar precio final",
    }


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
        "scene_state",
        "recent_memory_episodic_short",
        "trace_meta",
    }
    assert dumped["schema_version"] == "memory_input.v1"
    assert dumped["memory_working_current"] == state.memory_working.model_dump(mode="json")
    assert dumped["recent_memory_episodic_short"] == [x.model_dump(mode="json") for x in state.memory_episodic]
    assert dumped["scene_state"] == state.scene_state.model_dump(mode="json")
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
            "negotiation_state": _negotiation_base(),
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
            "negotiation_state": {
                **_negotiation_base(),
                "last_offer_other": {
                    "summary": "8500 euros",
                    "price_amount": 8500,
                    "currency": "EUR",
                    "extras": [],
                    "conditions": [],
                    "is_currently_active": True,
                    "source_turn_role": "user",
                },
            },
        }
    )

    apply_memory_output_to_state(state, output)

    assert state.memory_episodic[-1].event_summary == "acepta responder mañana"
    assert state.memory_working.current_topic == "seguimiento"
    assert state.memory_working.pending_question == "¿confirmas fecha?"
    assert state.memory_working.last_turn_summary == "aceptó responder mañana"
    assert state.negotiation_state.last_offer_other is not None
    assert state.negotiation_state.last_offer_other.price_amount == 8500


def test_memory_fallback_keeps_state_and_returns_valid_output():
    state = _build_state()
    fallback = _memory_fallback(state, "2")

    assert fallback.episodic_append == []
    assert fallback.working_memory_new.current_topic == state.memory_working.current_topic
    assert fallback.working_memory_new.pending_question == state.memory_working.pending_question
    assert fallback.negotiation_state == state.negotiation_state
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
                    "negotiation_state": _negotiation_base(),
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




def _iter_object_nodes(schema: object):
    if isinstance(schema, dict):
        if schema.get("type") == "object" or "properties" in schema:
            yield schema
        for value in schema.values():
            yield from _iter_object_nodes(value)
    elif isinstance(schema, list):
        for item in schema:
            yield from _iter_object_nodes(item)


def test_call_structured_normalizes_schema_required_for_all_object_properties():
    client = _FakeClient()
    _call_structured(
        client=client,
        model="gpt-5-nano",
        messages=[{"role": "developer", "content": "x"}],
        response_model=MemoryOutput,
        reasoning_effort="low",
        request_context={},
        store=False,
    )

    schema = client.responses.kwargs["text"]["format"]["schema"]
    for node in _iter_object_nodes(schema):
        properties = node.get("properties")
        if not isinstance(properties, dict):
            continue
        required = node.get("required")
        assert isinstance(required, list)
        assert set(required) == set(properties.keys())

    offer = schema["$defs"]["NegotiationOffer"]
    assert "summary" in offer["properties"]
    assert "summary" in offer["required"]

def test_memory_negotiation_case_a_user_offer_updates_last_offer_other():
    state = _build_state()
    output = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "precio", "pending_question": None, "last_turn_summary": "ofrece 8500"},
            "negotiation_state": {
                **_negotiation_base(),
                "last_offer_other": {
                    "summary": "Yo pensaba en 8500 euros",
                    "price_amount": 8500,
                    "currency": "EUR",
                    "extras": [],
                    "conditions": [],
                    "is_currently_active": True,
                    "source_turn_role": "user",
                },
            },
        }
    )
    apply_memory_output_to_state(state, output)
    assert state.negotiation_state.last_offer_other is not None
    assert state.negotiation_state.last_offer_other.price_amount == 8500


def test_memory_negotiation_case_b_keeps_self_and_other_offers_with_axes():
    state = _build_state()
    output = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "precio", "pending_question": None, "last_turn_summary": "contraoferta 8500 + ruedas"},
            "negotiation_state": {
                **_negotiation_base(),
                "active_axes": ["price", "extras"],
                "last_offer_self": {
                    "summary": "Propongo 8000",
                    "price_amount": 8000,
                    "currency": "EUR",
                    "extras": [],
                    "conditions": [],
                    "is_currently_active": True,
                    "source_turn_role": "assistant",
                },
                "last_offer_other": {
                    "summary": "Preferiría 8500 y te regalo un pack de 4 ruedas",
                    "price_amount": 8500,
                    "currency": "EUR",
                    "extras": ["pack de 4 ruedas"],
                    "conditions": [],
                    "is_currently_active": True,
                    "source_turn_role": "user",
                },
            },
        }
    )
    apply_memory_output_to_state(state, output)
    assert state.negotiation_state.last_offer_self is not None
    assert state.negotiation_state.last_offer_self.price_amount == 8000
    assert state.negotiation_state.last_offer_other is not None
    assert state.negotiation_state.last_offer_other.price_amount == 8500
    assert any("ruedas" in extra for extra in state.negotiation_state.last_offer_other.extras)
    assert {"price", "extras"}.issubset(set(state.negotiation_state.active_axes))


def test_memory_negotiation_case_c_reconstructs_last_offer_self_from_recent_context_and_planner_reads_it():
    state = _build_state()
    state.planner_state.current_phase = NegotiationPhase.propuesta_creativa
    output = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "cierre", "pending_question": None, "last_turn_summary": "propone 8350 y papeleo hoy"},
            "negotiation_state": {
                **_negotiation_base(),
                "active_axes": ["price", "paperwork", "closing_timing"],
                "last_offer_self": {
                    "summary": "8250 + ruedas",
                    "price_amount": 8250,
                    "currency": "EUR",
                    "extras": ["ruedas"],
                    "conditions": [],
                    "is_currently_active": True,
                    "source_turn_role": "assistant",
                },
                "last_offer_other": {
                    "summary": "8350 y hoy hacemos el papeleo",
                    "price_amount": 8350,
                    "currency": "EUR",
                    "extras": [],
                    "conditions": ["cierre hoy", "papeleo hoy"],
                    "is_currently_active": True,
                    "source_turn_role": "user",
                },
            },
        }
    )
    apply_memory_output_to_state(state, output)
    planner_input = build_planner_input(
        state,
        [],
        _build_user_turn("Lo dejamos en 8350 y hoy hacemos el papeleo", "2026-01-01T00:00:00Z"),
        {"turn_id": "12", "prompt_version": "planner_v3", "schema_version": "planner_input.v1", "model_target": "o4-mini"},
        "backend/negociacion/prompts",
    )
    assert planner_input.negotiation_state.last_offer_self is not None
    assert planner_input.negotiation_state.last_offer_self.price_amount == 8250
    assert planner_input.negotiation_state.last_offer_other is not None
    assert planner_input.negotiation_state.last_offer_other.price_amount == 8350
    assert any("papeleo" in cond or "hoy" in cond for cond in planner_input.negotiation_state.last_offer_other.conditions)
    assert "price" in planner_input.negotiation_state.active_axes
    assert "paperwork" in planner_input.negotiation_state.active_axes or "closing_timing" in planner_input.negotiation_state.active_axes


def test_memory_negotiation_case_d_tentative_agreement_reaches_planner():
    state = _build_state()
    state.planner_state.current_phase = NegotiationPhase.formalizacion_del_acuerdo
    output = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "cierre", "pending_question": None, "last_turn_summary": "acuerdo tentativo"},
            "negotiation_state": {
                **_negotiation_base(),
                "status": "tentative_agreement",
                "last_offer_self": {
                    "summary": "8250 + ruedas",
                    "price_amount": 8250,
                    "currency": "EUR",
                    "extras": ["ruedas"],
                    "conditions": [],
                    "is_currently_active": True,
                    "source_turn_role": "assistant",
                },
                "last_offer_other": {
                    "summary": "aceptado",
                    "price_amount": 8250,
                    "currency": "EUR",
                    "extras": ["ruedas"],
                    "conditions": ["cierre hoy"],
                    "is_currently_active": True,
                    "source_turn_role": "user",
                },
                "tentative_agreement": {
                    "summary": "acuerdo en 8250 con ruedas y papeleo hoy",
                    "price_amount": 8250,
                    "currency": "EUR",
                    "extras": ["ruedas"],
                    "conditions": ["papeleo hoy"],
                },
                "next_open_loop": "confirmar hora de firma",
            },
        }
    )
    apply_memory_output_to_state(state, output)
    planner_input = build_planner_input(
        state,
        [],
        _build_user_turn("Perfecto, hecho", "2026-01-01T00:00:00Z"),
        {"turn_id": "13", "prompt_version": "planner_v3", "schema_version": "planner_input.v1", "model_target": "o4-mini"},
        "backend/negociacion/prompts",
    )
    assert planner_input.negotiation_state.tentative_agreement is not None
    assert planner_input.negotiation_state.last_offer_self is not None
    assert planner_input.negotiation_state.last_offer_other is not None


def test_memory_stall_state_defaults_for_normal_active_negotiation():
    output = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "precio", "pending_question": None, "last_turn_summary": "contraoferta normal"},
            "negotiation_state": _negotiation_base(),
        }
    )

    assert output.negotiation_state.stall_state.is_hard_stalemate is False
    assert output.negotiation_state.stall_state.stalemate_reason is None
    assert output.negotiation_state.stall_state.self_ultimatum_active is False
    assert output.negotiation_state.stall_state.self_ultimatum_summary is None


def test_memory_stall_state_hard_stalemate_with_reason():
    output = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "precio", "pending_question": None, "last_turn_summary": "sin convergencia tras varias rondas"},
            "negotiation_state": {
                **_negotiation_base(),
                "stall_state": {
                    "is_hard_stalemate": True,
                    "stalemate_reason": "multiple_adjustments_without_convergence",
                    "self_ultimatum_active": False,
                    "self_ultimatum_summary": None,
                },
            },
        }
    )

    assert output.negotiation_state.stall_state.is_hard_stalemate is True
    assert output.negotiation_state.stall_state.stalemate_reason == "multiple_adjustments_without_convergence"


def test_memory_stall_state_assistant_ultimatum_active_with_summary():
    output = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "cierre", "pending_question": None, "last_turn_summary": "assistant marcó última propuesta"},
            "negotiation_state": {
                **_negotiation_base(),
                "stall_state": {
                    "is_hard_stalemate": True,
                    "stalemate_reason": "price_gap_persistent",
                    "self_ultimatum_active": True,
                    "self_ultimatum_summary": "Máximo 7000 EUR con garantía de 1 año",
                },
            },
        }
    )

    assert output.negotiation_state.stall_state.self_ultimatum_active is True
    assert output.negotiation_state.stall_state.self_ultimatum_summary is not None


def test_memory_stall_state_firm_counteroffer_is_not_ultimatum():
    output = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "precio", "pending_question": None, "last_turn_summary": "contraoferta firme"},
            "negotiation_state": {
                **_negotiation_base(),
                "stall_state": {
                    "is_hard_stalemate": False,
                    "stalemate_reason": None,
                    "self_ultimatum_active": False,
                    "self_ultimatum_summary": None,
                },
            },
        }
    )

    assert output.negotiation_state.stall_state.self_ultimatum_active is False


def test_canonical_state_includes_stall_state_defaults_and_schema_compatibility():
    state = build_default_canonical_state(session_id="s-stall", thread_mode=ThreadMode.conversation)

    assert state.negotiation_state.stall_state.is_hard_stalemate is False
    assert state.negotiation_state.stall_state.stalemate_reason is None
    assert state.negotiation_state.stall_state.self_ultimatum_active is False
    assert state.negotiation_state.stall_state.self_ultimatum_summary is None
