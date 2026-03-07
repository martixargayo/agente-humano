from __future__ import annotations

import json
from pathlib import Path

from negociacion.nodes.memory_node import DialogueMessage
from negociacion.nodes.phase_classifier_node import PhaseClassifierOutput
from negociacion.nodes.planner_node import PlannerOutput
from negociacion.orchestration.flow_config import (
    PHASE_CLASSIFIER_OUTPUT_SCHEMA_VERSION,
    _build_user_turn,
    _call_structured,
    _phase_classifier_fallback,
    _load_phase_cards,
    apply_phase_classifier_output_to_state,
    build_executor_input,
    build_phase_classifier_messages_payload,
    build_phase_input,
    build_planner_input,
)
from negociacion.state.canonical_state import build_default_canonical_state
from negociacion.state.shared_types import NegotiationPhase, StructuredCallSource, ThreadMode


def _build_state():
    state = build_default_canonical_state(session_id="s1", thread_mode=ThreadMode.conversation)
    state.planner_state.current_phase = NegotiationPhase.descubrimiento_y_comprension
    state.planner_state.previous_phase = NegotiationPhase.clima_humano
    state.planner_state.topics_touched_current_phase = ["precio"]
    state.planner_state.topics_touched_previous_phases = ["saludo"]
    return state


def test_build_phase_input_exact_fields_and_sources():
    state = _build_state()
    user_turn = _build_user_turn("Necesito revisar números", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "2",
        "prompt_version": "phase_classifier_v1",
        "schema_version": "phase_classifier_input.v1",
        "model_target": "gpt-5-mini",
    }
    recent = [
        DialogueMessage(role="assistant", text="¿Qué presupuesto tienes?"),
        DialogueMessage(role="user", text=user_turn.normalized_text),
    ]

    payload = build_phase_input(state, recent, user_turn, trace_meta)  # type: ignore[arg-type]
    dumped = payload.model_dump(mode="json")

    assert set(dumped.keys()) == {
        "schema_version",
        "previous_phase",
        "recent_phase_history",
        "recent_turns",
        "current_user_turn",
        "trace_meta",
    }
    assert dumped["schema_version"] == "phase_classifier_input.v1"
    assert dumped["previous_phase"] == "descubrimiento_y_comprension"
    assert dumped["recent_phase_history"] == ["clima_humano", "descubrimiento_y_comprension"]
    assert dumped["recent_turns"] == [{"role": "assistant", "text": "¿Qué presupuesto tienes?"}]


def test_phase_output_schema_contract():
    output = PhaseClassifierOutput.model_validate(
        {
            "schema_version": "phase_classifier.v1",
            "current_phase": "propuesta_creativa",
        }
    )
    assert output.schema_version == PHASE_CLASSIFIER_OUTPUT_SCHEMA_VERSION


def test_apply_phase_output_updates_only_current_previous_phase():
    state = _build_state()
    output = PhaseClassifierOutput(schema_version="phase_classifier.v1", current_phase=NegotiationPhase.propuesta_creativa)

    apply_phase_classifier_output_to_state(state, output)

    assert state.planner_state.previous_phase == NegotiationPhase.descubrimiento_y_comprension
    assert state.planner_state.current_phase == NegotiationPhase.propuesta_creativa
    assert state.planner_state.topics_touched_current_phase == ["precio"]
    assert state.planner_state.topics_touched_previous_phases == ["saludo"]


def test_phase_fallback_returns_valid_output_and_safe_default():
    out = _phase_classifier_fallback(None)
    assert out.schema_version == "phase_classifier.v1"
    assert out.current_phase == NegotiationPhase.clima_humano


class _FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.refusal = None


class _FakeResponsesAPI:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _FakeResponse(json.dumps({"schema_version": "phase_classifier.v1", "current_phase": "propuesta_creativa"}))


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponsesAPI()


def test_phase_messages_are_split_and_structured_call_is_strict_json_schema():
    state = _build_state()
    user_turn = _build_user_turn("Propongo 1200", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "3",
        "prompt_version": "phase_classifier_v1",
        "schema_version": "phase_classifier_input.v1",
        "model_target": "gpt-5-mini",
    }
    payload = build_phase_input(state, [], user_turn, trace_meta)  # type: ignore[arg-type]
    messages = build_phase_classifier_messages_payload("PROMPT", payload)

    assert messages[0]["role"] == "developer"
    assert messages[1]["role"] == "user"
    assert "<phase_classifier_input_json>" in messages[1]["content"]

    client = _FakeClient()
    result = _call_structured(
        client=client,
        model="gpt-5-mini",
        messages=messages,
        response_model=PhaseClassifierOutput,
        reasoning_effort="low",
        request_context={},
        store=False,
    )

    assert result.source == StructuredCallSource.model
    assert client.responses.kwargs["text"]["format"]["type"] == "json_schema"
    assert client.responses.kwargs["text"]["format"]["strict"] is True


def test_phase_cards_placeholder_file_exists_and_has_all_phases():
    cards = _load_phase_cards("backend/negociacion/prompts")
    assert set(cards.keys()) == {
        NegotiationPhase.clima_humano,
        NegotiationPhase.descubrimiento_y_comprension,
        NegotiationPhase.propuesta_creativa,
        NegotiationPhase.concesiones_y_ajuste_final,
        NegotiationPhase.formalizacion_del_acuerdo,
    }

    path = Path("backend/negociacion/prompts/phase_cards.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw.keys()) == {
        "clima_humano",
        "descubrimiento_y_comprension",
        "propuesta_creativa",
        "concesiones_y_ajuste_final",
        "formalizacion_del_acuerdo",
    }


def test_phase_cards_custom_prompts_dir_is_used_by_planner_and_executor(tmp_path):
    cards_path = tmp_path / "phase_cards.json"
    cards_path.write_text(
        json.dumps(
            {
                "clima_humano": {
                    "phase_id": "clima_humano",
                    "objective": "OBJETIVO CUSTOM CLIMA",
                    "normal_moves": ["m1"],
                    "stay_in_phase_when": ["s1"],
                    "exit_phase_when": ["e1"],
                },
                "descubrimiento_y_comprension": {
                    "phase_id": "descubrimiento_y_comprension",
                    "objective": "d",
                    "normal_moves": [],
                    "stay_in_phase_when": [],
                    "exit_phase_when": [],
                },
                "propuesta_creativa": {
                    "phase_id": "propuesta_creativa",
                    "objective": "p",
                    "normal_moves": [],
                    "stay_in_phase_when": [],
                    "exit_phase_when": [],
                },
                "concesiones_y_ajuste_final": {
                    "phase_id": "concesiones_y_ajuste_final",
                    "objective": "c",
                    "normal_moves": [],
                    "stay_in_phase_when": [],
                    "exit_phase_when": [],
                },
                "formalizacion_del_acuerdo": {
                    "phase_id": "formalizacion_del_acuerdo",
                    "objective": "f",
                    "normal_moves": [],
                    "stay_in_phase_when": [],
                    "exit_phase_when": [],
                },
            }
        ),
        encoding="utf-8",
    )

    state = _build_state()
    state.planner_state.current_phase = NegotiationPhase.clima_humano
    user_turn = _build_user_turn("hola", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "4",
        "prompt_version": "v",
        "schema_version": "planner_input.v1",
        "model_target": "gpt-5-mini",
    }

    planner_input = build_planner_input(state, [], user_turn, trace_meta, str(tmp_path))  # type: ignore[arg-type]

    planner_output = PlannerOutput.model_validate(
        {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": "g",
            "decision": "hold",
            "content_plan": {"must_include": ["x"], "must_avoid": ["y"]},
            "limits": {
                "max_sentences": 3,
                "max_questions": 1,
                "allow_topic_shift": False,
                "allow_personal_disclosure": False,
            },
            "memory_targets": [],
            "done_criteria": ["ok"],
        }
    )

    executor_input = build_executor_input(
        state,
        [],
        planner_output,
        user_turn,
        trace_meta,
        4,
        str(tmp_path),
    )  # type: ignore[arg-type]

    assert "OBJETIVO CUSTOM CLIMA" in planner_input.phase_card.guidance
    assert "OBJETIVO CUSTOM CLIMA" in executor_input.phase_card.guidance
