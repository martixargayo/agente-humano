from __future__ import annotations

import json
from pathlib import Path

from negociacion.nodes.memory_node import DialogueMessage
from negociacion.nodes.planner_node import PlannerOutput
from negociacion.orchestration.flow_config import (
    _build_user_turn,
    _call_structured,
    _planner_fallback,
    apply_planner_output_to_state,
    build_executor_input,
    build_planner_input,
    build_planner_messages,
)
from negociacion.state import canonical_state as canonical_state_module
from negociacion.state.canonical_state import build_default_canonical_state
from negociacion.state.shared_types import NegotiationPhase, StructuredCallSource, ThreadMode


def _build_state():
    state = build_default_canonical_state(session_id="s1", thread_mode=ThreadMode.conversation)
    state.planner_state.current_phase = NegotiationPhase.descubrimiento_y_comprension
    state.planner_state.previous_phase = NegotiationPhase.clima_humano
    state.memory_working.current_topic = "precio"
    state.negotiation_state.blockers = ["falta presupuesto"]
    return state


def test_build_planner_input_exact_fields_and_sources():
    state = _build_state()
    user_turn = _build_user_turn("Necesito una propuesta", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "10",
        "prompt_version": "planner_v3",
        "schema_version": "planner_input.v1",
        "model_target": "o4-mini",
    }
    recent = [
        DialogueMessage(role="assistant", text="¿qué rango manejas?"),
        DialogueMessage(role="user", text="necesito una propuesta"),
    ]

    payload = build_planner_input(state, recent, user_turn, trace_meta, "backend/negociacion/prompts")  # type: ignore[arg-type]
    dumped = payload.model_dump(mode="json")

    assert set(dumped.keys()) == {
        "schema_version",
        "task_contract",
        "persona_policy",
        "current_phase",
        "phase_card",
        "user_turn",
        "recent_dialogue_short",
        "memory_working",
        "negotiation_state",
        "planner_state",
        "scene_state",
        "selected_memory",
        "trace_meta",
    }
    assert dumped["task_contract"]["node_name"] == "planner"
    assert dumped["task_contract"]["output_schema_version"] == "planner.v3"
    assert dumped["persona_policy"] == state.persona.policy.model_dump(mode="json")
    assert dumped["current_phase"] == state.planner_state.current_phase.value
    assert dumped["scene_state"] == state.scene_state.model_dump(mode="json")






def test_build_planner_input_injects_full_phase_card_from_source_of_truth():
    state = _build_state()
    state.planner_state.current_phase = NegotiationPhase.clima_humano
    user_turn = _build_user_turn("hola", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "10b",
        "prompt_version": "planner_v3",
        "schema_version": "planner_input.v1",
        "model_target": "o4-mini",
    }

    payload = build_planner_input(state, [], user_turn, trace_meta, "backend/negociacion/prompts")  # type: ignore[arg-type]
    phase_card = payload.model_dump(mode="json")["phase_card"]

    assert phase_card["phase"] == "clima_humano"
    assert phase_card["phase_objective"].startswith("Mantener una interacción humana breve")
    assert "what_good_progress_looks_like" in phase_card
    assert "planner_bias" in phase_card
    assert "good_moves" in phase_card
    assert "avoid" in phase_card
    assert phase_card["question_policy"]["default_max_questions"] == 0
    assert "done_signals" in phase_card
    assert phase_card.get("guidance")
def test_planner_output_fields_are_exact_and_forbid_legacy_keys():
    assert set(PlannerOutput.model_fields.keys()) == {
        "schema_version",
        "status",
        "turn_goal",
        "decision",
        "content_plan",
        "limits",
        "memory_targets",
        "done_criteria",
    }

    prohibited = {
        "current_phase",
        "style_band",
        "conversation_act",
        "confidence",
        "reasoning",
        "rationale",
        "explanation",
    }
    assert prohibited.isdisjoint(PlannerOutput.model_fields.keys())


def test_planner_output_json_schema_marks_memory_targets_as_required_for_strict_mode():
    schema = PlannerOutput.model_json_schema()
    required = set(schema.get("required", []))
    properties = set(schema.get("properties", {}).keys())

    assert "memory_targets" in required
    assert required == properties

def test_planner_output_schema_contract_and_message_split():
    output = PlannerOutput.model_validate(
        {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": "proponer siguiente paso",
            "decision": "counter",
            "content_plan": {"must_include": ["un paso"], "must_avoid": ["inventar hechos"]},
            "limits": {
                "max_sentences": 3,
                "max_questions": 1,
                "allow_topic_shift": False,
                "allow_personal_disclosure": False,
            },
            "memory_targets": [],
            "done_criteria": ["objetivo_cubierto"],
        }
    )
    assert output.schema_version == "planner.v3"

    state = _build_state()
    user_turn = _build_user_turn("texto", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "11",
        "prompt_version": "planner_v3",
        "schema_version": "planner_input.v1",
        "model_target": "o4-mini",
    }
    payload = build_planner_input(state, [], user_turn, trace_meta, "backend/negociacion/prompts")  # type: ignore[arg-type]
    messages = build_planner_messages("PROMPT", payload)

    assert messages[0]["role"] == "developer"
    assert messages[1]["role"] == "user"
    assert "<planner_input_json>" in messages[1]["content"]


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
                    "schema_version": "planner.v3",
                    "status": "clarify",
                    "turn_goal": "pedir dato",
                    "decision": "ask",
                    "content_plan": {"must_include": ["pregunta"], "must_avoid": ["inventar hechos"]},
                    "limits": {
                        "max_sentences": 2,
                        "max_questions": 1,
                        "allow_topic_shift": False,
                        "allow_personal_disclosure": False,
                    },
                    "memory_targets": [],
                    "done_criteria": ["dato_solicitado"],
                }
            )
        )


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponsesAPI()


def test_planner_structured_call_is_strict_json_schema():
    client = _FakeClient()
    result = _call_structured(
        client=client,
        model="o4-mini",
        messages=[{"role": "developer", "content": "x"}],
        response_model=PlannerOutput,
        reasoning_effort="medium",
        request_context={},
        store=True,
    )

    assert result.source == StructuredCallSource.model
    assert client.responses.kwargs["text"]["format"]["type"] == "json_schema"
    assert client.responses.kwargs["text"]["format"]["strict"] is True


def test_apply_planner_output_to_state_only_updates_current_turn_goal():
    state = _build_state()
    before = state.planner_state.model_dump(mode="json")
    output = PlannerOutput.model_validate(
        {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": "cerrar siguiente paso",
            "decision": "close",
            "content_plan": {"must_include": ["cierre"], "must_avoid": ["inventar"]},
            "limits": {
                "max_sentences": 3,
                "max_questions": 0,
                "allow_topic_shift": False,
                "allow_personal_disclosure": False,
            },
            "memory_targets": ["x"],
            "done_criteria": ["ok"],
        }
    )

    apply_planner_output_to_state(state, output)

    assert state.planner_state.current_turn_goal == "cerrar siguiente paso"
    assert state.planner_state.current_phase.value == before["current_phase"]
    assert state.planner_state.previous_phase.value == before["previous_phase"]
    assert state.planner_state.topics_touched_current_phase == before["topics_touched_current_phase"]
    assert state.planner_state.topics_touched_previous_phases == before["topics_touched_previous_phases"]


def test_planner_fallback_is_valid_and_conservative():
    out = _planner_fallback()
    assert out.schema_version == "planner.v3"
    assert out.status == "clarify"
    assert out.decision == "ask"
    assert out.memory_targets == []
    assert out.limits.allow_topic_shift is False


def test_persona_file_exists_and_default_state_uses_it():
    path = Path("backend/negociacion/prompts/persona.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "policy" in raw
    assert "expressive" in raw

    state = build_default_canonical_state(session_id="s100", thread_mode=ThreadMode.conversation)
    assert state.persona.policy.identidad_operativa == raw["policy"]["identidad_operativa"]
    assert state.persona.expressive.voz_y_estilo == raw["expressive"]["voz_y_estilo"]
    assert state.scene_state.copresent is True
    assert state.scene_state.encounter_in_progress is True
    assert state.scene_state.conversation_only is True




def test_default_state_uses_emergency_persona_if_file_missing(monkeypatch):
    original_read_text = canonical_state_module.Path.read_text

    def _fake_read_text(self, *args, **kwargs):
        if self.name == "persona.json":
            raise FileNotFoundError("missing persona")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(canonical_state_module.Path, "read_text", _fake_read_text)

    state = build_default_canonical_state(session_id="smissing", thread_mode=ThreadMode.conversation)
    assert state.persona.policy.identidad_operativa == canonical_state_module.EMERGENCY_PERSONA_DEFAULTS["policy"]["identidad_operativa"]


def test_default_state_uses_emergency_persona_if_json_invalid(monkeypatch):
    original_read_text = canonical_state_module.Path.read_text

    def _fake_read_text(self, *args, **kwargs):
        if self.name == "persona.json":
            return "{invalid-json"
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(canonical_state_module.Path, "read_text", _fake_read_text)

    state = build_default_canonical_state(session_id="sinvalid", thread_mode=ThreadMode.conversation)
    assert state.persona.expressive.naturalidad == canonical_state_module.EMERGENCY_PERSONA_DEFAULTS["expressive"]["naturalidad"]


def test_default_state_uses_emergency_persona_if_structure_invalid(monkeypatch):
    original_read_text = canonical_state_module.Path.read_text

    def _fake_read_text(self, *args, **kwargs):
        if self.name == "persona.json":
            return json.dumps({"policy": "not-an-object", "expressive": {}})
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(canonical_state_module.Path, "read_text", _fake_read_text)

    state = build_default_canonical_state(session_id="sstructure", thread_mode=ThreadMode.conversation)
    assert state.persona.policy.objetivo_privado == canonical_state_module.EMERGENCY_PERSONA_DEFAULTS["policy"]["objetivo_privado"]

def test_planner_uses_policy_and_executor_uses_expressive_from_canonical():
    state = _build_state()
    state.persona.policy.identidad_operativa = "perfil_test_policy"
    state.persona.expressive.voz_y_estilo = "perfil_test_expressive"

    user_turn = _build_user_turn("hola", "2026-01-01T00:00:00Z")
    trace_meta = {
        "turn_id": "12",
        "prompt_version": "planner_v3",
        "schema_version": "planner_input.v1",
        "model_target": "o4-mini",
    }
    planner_input = build_planner_input(state, [], user_turn, trace_meta, "backend/negociacion/prompts")  # type: ignore[arg-type]

    planner_output = PlannerOutput.model_validate(
        {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": "g",
            "decision": "hold",
            "content_plan": {"must_include": ["x"], "must_avoid": ["y"]},
            "limits": {
                "max_sentences": 6,
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
        "backend/negociacion/prompts",
    )  # type: ignore[arg-type]

    assert planner_input.persona_policy.identidad_operativa == "perfil_test_policy"
    assert executor_input.persona_expressive.voz_y_estilo == "perfil_test_expressive"
