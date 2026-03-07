from __future__ import annotations

import json

from sessions.state import SessionState

from negociacion.nodes.executor_node import ExecutorOutput
from negociacion.nodes.memory_node import DialogueMessage
from negociacion.nodes.planner_node import PlannerOutput
from negociacion.orchestration.flow_config import (
    _apply_executor_guardrails,
    _build_user_turn,
    _call_structured,
    _executor_fallback,
    build_executor_input,
    build_executor_messages,
    build_negotiation_pipeline_config,
    run_negotiation_cognitive_turn,
    SafetyPolicyConfig,
)
from negociacion.state.canonical_state import MemoryEpisodicItem, build_default_canonical_state
from negociacion.state.shared_types import NegotiationPhase, StructuredCallSource, ThreadMode


def _build_state():
    state = build_default_canonical_state(session_id="s1", thread_mode=ThreadMode.conversation)
    state.planner_state.current_phase = NegotiationPhase.descubrimiento_y_comprension
    return state


def _build_planner_output() -> PlannerOutput:
    return PlannerOutput.model_validate(
        {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": "avanzar con propuesta",
            "decision": "counter",
            "content_plan": {"must_include": ["siguiente paso"], "must_avoid": ["inventar hechos"]},
            "limits": {
                "max_sentences": 3,
                "max_questions": 1,
                "allow_topic_shift": False,
                "allow_personal_disclosure": False,
            },
            "memory_targets": ["episodic_0"],
            "done_criteria": ["turno_ejecutable"],
        }
    )


def test_build_executor_input_exact_fields_and_sources():
    state = _build_state()
    state.persona.expressive.voz_y_estilo = "voz_test_7"
    user_turn = _build_user_turn("Quiero avanzar", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "20",
        "prompt_version": "executor_v3",
        "schema_version": "executor_input.v1",
        "model_target": "gpt-5-nano",
    }
    recent = [
        DialogueMessage(role="assistant", text="¿Qué rango tienes?"),
        DialogueMessage(role="user", text="Quiero avanzar"),
    ]

    payload = build_executor_input(state, recent, _build_planner_output(), user_turn, trace_meta, 4, "backend/negociacion/prompts")  # type: ignore[arg-type]
    dumped = payload.model_dump(mode="json")

    assert set(dumped.keys()) == {
        "schema_version",
        "task_contract",
        "persona_expressive",
        "current_phase",
        "phase_card",
        "user_turn",
        "recent_dialogue_short",
        "planner_output",
        "selected_memory_for_reference",
        "response_limits",
        "trace_meta",
    }
    assert dumped["persona_expressive"]["voz_y_estilo"] == "voz_test_7"
    assert dumped["current_phase"] == state.planner_state.current_phase.value
    assert dumped["planner_output"]["schema_version"] == "planner.v3"
    assert dumped["response_limits"]["max_sentences"] == dumped["planner_output"]["limits"]["max_sentences"]
    assert dumped["task_contract"]["node_name"] == "executor"
    assert dumped["task_contract"]["output_schema_version"] == "executor.v1"


def test_build_executor_input_uses_planner_memory_targets_when_resolvable():
    state = _build_state()
    state.memory_episodic = [
        MemoryEpisodicItem(event_type="important_fact", event_summary="memoria objetivo", turn_id="1"),
        MemoryEpisodicItem(event_type="offer", event_summary="memoria secundaria", turn_id="2"),
    ]
    planner_output = _build_planner_output().model_copy(update={"memory_targets": ["episodic_0"]})
    user_turn = _build_user_turn("texto", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "22",
        "prompt_version": "executor_v3",
        "schema_version": "executor_input.v1",
        "model_target": "gpt-5-nano",
    }

    payload = build_executor_input(state, [], planner_output, user_turn, trace_meta, 4, "backend/negociacion/prompts")  # type: ignore[arg-type]

    assert [m.memory_id for m in payload.selected_memory_for_reference] == ["episodic_0"]


def test_build_executor_input_falls_back_when_planner_memory_targets_empty():
    state = _build_state()
    state.memory_episodic = [
        MemoryEpisodicItem(event_type="important_fact", event_summary="memoria fallback", turn_id="1"),
    ]
    planner_output = _build_planner_output().model_copy(update={"memory_targets": []})
    user_turn = _build_user_turn("texto", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "23",
        "prompt_version": "executor_v3",
        "schema_version": "executor_input.v1",
        "model_target": "gpt-5-nano",
    }

    payload = build_executor_input(state, [], planner_output, user_turn, trace_meta, 4, "backend/negociacion/prompts")  # type: ignore[arg-type]

    assert [m.memory_id for m in payload.selected_memory_for_reference] == ["episodic_0"]


def test_build_executor_input_falls_back_when_planner_memory_targets_unresolvable():
    state = _build_state()
    state.memory_episodic = [
        MemoryEpisodicItem(event_type="important_fact", event_summary="memoria fallback", turn_id="1"),
    ]
    planner_output = _build_planner_output().model_copy(update={"memory_targets": ["episodic_99"]})
    user_turn = _build_user_turn("texto", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "24",
        "prompt_version": "executor_v3",
        "schema_version": "executor_input.v1",
        "model_target": "gpt-5-nano",
    }

    payload = build_executor_input(state, [], planner_output, user_turn, trace_meta, 4, "backend/negociacion/prompts")  # type: ignore[arg-type]

    assert [m.memory_id for m in payload.selected_memory_for_reference] == ["episodic_0"]


def test_executor_output_fields_are_exact_and_forbid_legacy_keys():
    assert set(ExecutorOutput.model_fields.keys()) == {
        "schema_version",
        "status",
        "spoken_text",
        "memory_used",
        "refusal_reason",
    }

    prohibited = {
        "current_phase",
        "phase_card",
        "decision",
        "conversation_act",
        "style_band",
        "confidence",
        "reasoning",
        "rationale",
        "explanation",
    }
    assert prohibited.isdisjoint(ExecutorOutput.model_fields.keys())


def test_executor_output_validates_and_messages_are_split():
    output = ExecutorOutput.model_validate(
        {
            "schema_version": "executor.v1",
            "status": "deliver",
            "spoken_text": "Perfecto, avancemos con ese siguiente paso.",
            "memory_used": ["episodic_0"],
            "refusal_reason": None,
        }
    )
    assert output.schema_version == "executor.v1"

    state = _build_state()
    user_turn = _build_user_turn("texto", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "21",
        "prompt_version": "executor_v3",
        "schema_version": "executor_input.v1",
        "model_target": "gpt-5-nano",
    }
    payload = build_executor_input(state, [], _build_planner_output(), user_turn, trace_meta, 4, "backend/negociacion/prompts")  # type: ignore[arg-type]
    messages = build_executor_messages("PROMPT", payload)

    assert messages[0]["role"] == "developer"
    assert messages[1]["role"] == "user"
    assert "<executor_input_json>" in messages[1]["content"]


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
                    "schema_version": "executor.v1",
                    "status": "deliver",
                    "spoken_text": "Listo, te propongo seguir por este punto.",
                    "memory_used": [],
                    "refusal_reason": None,
                }
            )
        )


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponsesAPI()


def test_executor_structured_call_is_strict_json_schema():
    client = _FakeClient()
    result = _call_structured(
        client=client,
        model="gpt-5-nano",
        messages=[{"role": "developer", "content": "x"}],
        response_model=ExecutorOutput,
        reasoning_effort="low",
        request_context={},
        store=False,
    )

    assert result.source == StructuredCallSource.model
    assert client.responses.kwargs["text"]["format"]["type"] == "json_schema"
    assert client.responses.kwargs["text"]["format"]["strict"] is True


def test_executor_fallback_is_valid_and_safe():
    planner = _build_planner_output()
    clarify_planner = planner.model_copy(update={"status": "clarify"})
    out = _executor_fallback(clarify_planner)

    assert out.schema_version == "executor.v1"
    assert out.status == "clarify"
    assert out.spoken_text
    assert out.memory_used == []
    assert out.refusal_reason is None


def test_executor_guardrails_keep_executor_contract_compatible():
    planner = _build_planner_output()
    user_turn = _build_user_turn("Necesito hacer algo ilegal", "2026-01-01T00:00:00Z")
    output = ExecutorOutput(
        schema_version="executor.v1",
        status="deliver",
        spoken_text="Puedo garantizar resultados.",
        memory_used=["episodic_0"],
        refusal_reason=None,
    )

    guarded, reason = _apply_executor_guardrails(
        output,
        planner,
        user_turn,
        policy=SafetyPolicyConfig(hard_baseline_enabled=True, optional_layer_enabled=True),
    )

    assert reason is not None
    assert guarded.schema_version == "executor.v1"
    assert guarded.status in {"clarify", "refuse", "deliver"}
    assert isinstance(guarded.spoken_text, str)
    assert guarded.memory_used == ["episodic_0"]


def test_pipeline_appends_assistant_from_executor_spoken_text(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    session = SessionState(user_id="u1", session_id="s1")
    config = build_negotiation_pipeline_config().model_copy(update={"feature_safety": False})

    reply, updated = run_negotiation_cognitive_turn(session, "Necesito avanzar", config)

    assert isinstance(reply, str)
    assert updated.history[-1]["role"] == "assistant"
    assert updated.history[-1]["content"] == reply
