from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from conversacion_simple.orchestration.pipeline import (
    SummarizerOutput,
    StructuredBrainCall,
    _call_brain_structured,
    _call_summarizer_structured,
    _normalize_schema_for_strict_json_schema,
    run_conversacion_simple_turn,
)
from conversacion_simple.nodes.brain_node import BrainOutput
from conversacion_simple.services import build_conversacion_simple_turn_context
from sessions.state import SessionState


def _bind(state: SessionState, context_id: str = "baseline") -> None:
    state.world_state["conversacion_simple_context"] = {
        "flow_id": "conversacion_simple",
        "context_id": context_id,
        "context_version": "1.0.0",
    }


def _valid_brain_output() -> dict:
    return {
        "schema_version": "brain.v1",
        "status": "deliver",
        "assistant_response": {"text": "respuesta brain"},
        "state_patch": {
            "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "avanzar"},
            "memory_working": {"current_topic": "tema", "pending_question": None, "last_turn_summary": "resumen"},
            "memory_episodic_append": [
                {"event_type": "important_fact", "event_summary": "hecho", "turn_id": "t1"}
            ],
        },
        "observability": {"rationale_summary": "ok"},
    }


def _collect_required_mismatches(schema: object) -> list[tuple[str, list[str]]]:
    mismatches: list[tuple[str, list[str]]] = []

    def _walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                required = node.get("required")
                required_items = required if isinstance(required, list) else []
                missing = [key for key in properties.keys() if key not in required_items]
                if missing:
                    mismatches.append((path, missing))
            for key, value in node.items():
                _walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                _walk(value, f"{path}[{idx}]")

    _walk(schema, "$")
    return mismatches


def test_single_llm_call_per_turn(monkeypatch) -> None:
    calls = {"count": 0}

    def _fake_call(**kwargs):
        calls["count"] += 1
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output(), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, meta = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    assert calls["count"] == 1
    assert reply == "respuesta brain"
    assert meta["pipeline_topology"] == "single_llm"
    assert meta["node_names"] == ["brain"]
    assert meta["llm_call_count"] in {0, 1}
    assert updated.world_state[config.traces_key][-1]["pipeline_topology"] == "single_llm"


def test_invalid_brain_output_schema_raises(monkeypatch) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json={"schema_version": "brain.v1", "status": "deliver"}, response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    with pytest.raises(RuntimeError, match="conversacion_simple_brain_output_validation_error"):
        run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)


def test_legacy_response_text_payload_is_coerced(monkeypatch) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json={"response_text": "hola desde legacy"}, response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    assert reply == "hola desde legacy"
    assert updated.world_state[config.memory_key]["trace"]["last_status"] == "deliver"


@pytest.mark.parametrize(
    ("payload", "expected_reply", "expected_topic"),
    [
        (
            {
                "schema_version": "brain.v1",
                "status": "deliver",
                "assistant_response": {"text": "canon"},
                "state_patch": {
                    "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "g"},
                    "memory_working": {"current_topic": "topic-canon", "pending_question": None, "last_turn_summary": "s"},
                    "memory_episodic_append": [],
                },
            },
            "canon",
            "topic-canon",
        ),
        ({"response_text": "legacy-response-text"}, "legacy-response-text", None),
        ({"response": "legacy-response-string"}, "legacy-response-string", None),
        (
            {
                "response": {"text": "legacy-response-object"},
                "memory_patch": {"current_topic": "topic-memory-patch"},
            },
            "legacy-response-object",
            "topic-memory-patch",
        ),
        (
            {
                "assistant_response_text": "legacy-assistant-response-text",
                "memory_working_patch": {"current_topic": "topic-working-patch"},
            },
            "legacy-assistant-response-text",
            "topic-working-patch",
        ),
        (
            {
                "assistant": {"text": "legacy-assistant-object"},
                "state_patch": {"memory_episodic_append": []},
            },
            "legacy-assistant-object",
            None,
        ),
        (
            {
                "reply": "legacy-reply",
                "response_text": "ignored-when-reply-present",
                "state_patch": {"conversation_state": {"phase": "opening"}},
                "memory_patch": {"current_topic": "topic-combined"},
            },
            "legacy-reply",
            "topic-combined",
        ),
    ],
)
def test_brain_output_canonicalization_family_variants(monkeypatch, payload: dict, expected_reply: str, expected_topic: str | None) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=payload, response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
    canonical = updated.world_state[config.memory_key]

    assert reply == expected_reply
    if expected_topic is not None:
        assert canonical["memory_working"]["current_topic"] == expected_topic


@pytest.mark.parametrize(
    ("legacy_phase", "expected_phase"),
    [
        ("in_progress", "desarrollo"),
        ("active", "desarrollo"),
        ("opening", "apertura"),
        ("closing", "cierre"),
    ],
)
def test_legacy_response_key_and_phase_aliases_are_normalized(monkeypatch, legacy_phase: str, expected_phase: str) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(
            source="model",
            parsed_json={
                "response": "hola desde response",
                "schema_version": "brain.v1",
                "status": "deliver",
                "state_patch": {"conversation_state": {"phase": legacy_phase}},
            },
            response=None,
        )

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
    canonical = updated.world_state[config.memory_key]

    assert reply == "hola desde response"
    assert canonical["conversation_state"]["phase"] == expected_phase
    assert canonical["conversation_state"]["status"] == "active"


def test_unknown_phase_keeps_strict_validation(monkeypatch) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(
            source="model",
            parsed_json={
                "response": "hola",
                "schema_version": "brain.v1",
                "status": "deliver",
                "state_patch": {"conversation_state": {"phase": "unexpected_phase"}},
            },
            response=None,
        )

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    with pytest.raises(RuntimeError, match="conversacion_simple_brain_output_validation_error"):
        run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)


def test_legacy_memory_patch_and_response_object_are_normalized(monkeypatch) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(
            source="model",
            parsed_json={
                "schema_version": "brain.v1",
                "status": "deliver",
                "response": {"text": "respuesta legacy object"},
                "memory_patch": {
                    "current_topic": "tema legacy",
                    "pending_question": "pregunta legacy",
                    "last_turn_summary": "resumen legacy",
                },
            },
            response=None,
        )

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
    canonical = updated.world_state[config.memory_key]

    assert reply == "respuesta legacy object"
    assert canonical["memory_working"]["current_topic"] == "tema legacy"
    assert canonical["memory_working"]["pending_question"] == "pregunta legacy"
    assert canonical["memory_working"]["last_turn_summary"] == "resumen legacy"


def test_unknown_extra_fields_stay_strict_and_fail(monkeypatch) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(
            source="model",
            parsed_json={
                "schema_version": "brain.v1",
                "status": "deliver",
                "assistant_response": {"text": "ok"},
                "state_patch": {
                    "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "g"},
                    "memory_working": {"current_topic": "tema", "pending_question": None, "last_turn_summary": "resumen"},
                    "memory_episodic_append": [],
                },
                "totally_unknown_field": {"x": 1},
            },
            response=None,
        )

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    with pytest.raises(RuntimeError, match="conversacion_simple_brain_output_validation_error"):
        run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)


def test_fallback_without_openai_key_returns_clarify() -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, meta = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    assert meta["llm_call_count"] == 0
    assert isinstance(meta.get("response_id"), (str, type(None)))
    assert updated.world_state[config.memory_key]["trace"]["last_status"] in {"clarify", "deliver", "refuse"}
    assert isinstance(reply, str) and reply


def test_recent_dialogue_updated() -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    recent = updated.world_state[config.recent_dialogue_key]
    assert len(recent) >= 2
    assert recent[-2]["role"] == "user"
    assert recent[-1]["role"] == "assistant"
    assert isinstance(reply, str) and reply


def test_structured_call_enforces_json_schema_without_prompt_embedded_schema() -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        id = "resp_1"
        output_text = (
            '{"schema_version":"brain.v1","status":"deliver","assistant_response":{"text":"ok"},'
            '"state_patch":{"conversation_state":{"phase":"desarrollo","status":"active","current_turn_goal":"g"},'
            '"memory_working":{"current_topic":null,"pending_question":null,"last_turn_summary":"s"},'
            '"memory_episodic_append":[]},"observability":{"rationale_summary":"ok"}}'
        )

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeResponse()

    class _FakeClient:
        responses = _FakeResponses()

    out = _call_brain_structured(
        client=_FakeClient(),
        model="gpt-5-nano",
        messages=[{"role": "developer", "content": "prompt"}, {"role": "user", "content": "payload"}],
    )

    assert out.source == "model"
    assert out.parsed_json is not None
    text = captured.get("text")
    assert isinstance(text, dict)
    fmt = text.get("format")
    assert isinstance(fmt, dict)
    assert fmt.get("type") == "json_schema"
    assert fmt.get("strict") is True
    schema = fmt.get("schema")
    assert isinstance(schema, dict)
    assert _collect_required_mismatches(schema) == []
    assert schema.get("additionalProperties") is False
    assert isinstance(out.schema_observability, dict)
    assert out.schema_observability.get("schema_name") == "BrainOutput"
    assert out.schema_observability.get("validation", {}).get("valid") is True


def test_normalized_brain_output_schema_preserves_required_lists() -> None:
    base = BrainOutput.model_json_schema()
    normalized = _normalize_schema_for_strict_json_schema(base)
    assert _collect_required_mismatches(normalized) == []
    assert "observability" in normalized.get("required", [])
    assert "rationale_summary" in normalized.get("$defs", {}).get("BrainObservability", {}).get("required", [])


def test_normalized_summarizer_output_schema_has_full_required() -> None:
    normalized = _normalize_schema_for_strict_json_schema(SummarizerOutput.model_json_schema())
    assert _collect_required_mismatches(normalized) == []


def test_structured_summarizer_wiring_keeps_json_schema_strict_and_additional_properties() -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        id = "resp_summary_1"
        output_text = (
            '{"schema_version":"memory_summary.v1","situation_live":"ok","active_proposal":null,'
            '"latest_offer_each_side":[],"concessions_accumulated":[],"open_items":[],"closed_items":[],'
            '"operative_constraints":[],"fixed_time_calculations":[],"operative_question_live":null,'
            '"sensitive_info_exposed":[],"agreement_progress":null,"pending_inconsistencies":[],"uncertainties":[]}'
        )

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeResponse()

    class _FakeClient:
        responses = _FakeResponses()

    out = _call_summarizer_structured(
        client=_FakeClient(),
        model="gpt-5-nano",
        messages=[{"role": "developer", "content": "prompt"}, {"role": "user", "content": "payload"}],
    )

    assert out.source == "model"
    text = captured.get("text")
    assert isinstance(text, dict)
    fmt = text.get("format")
    assert isinstance(fmt, dict)
    assert fmt.get("type") == "json_schema"
    assert fmt.get("strict") is True
    assert isinstance(out.schema_observability, dict)
    assert out.schema_observability.get("schema_name") == "SummarizerOutput"
    assert out.schema_observability.get("validation", {}).get("valid") is True


def test_structured_call_provider_error_keeps_schema_observability() -> None:
    class _FailingResponses:
        def create(self, **kwargs):
            raise RuntimeError(
                "Error code: 400 - {'error': {'message': \"Invalid schema for response_format 'BrainOutput': "
                "In context=(), 'required' is required to be supplied and to be an array including every key in properties. "
                "Extra required key 'memory_episodic_append' supplied.\", 'type': 'invalid_request_error', "
                "'param': 'text.format.schema', 'code': 'invalid_json_schema'}}"
            )

    class _FailingClient:
        responses = _FailingResponses()

    out = _call_brain_structured(
        client=_FailingClient(),
        model="gpt-5-nano",
        messages=[{"role": "developer", "content": "prompt"}, {"role": "user", "content": "payload"}],
    )

    assert out.source == "fallback"
    assert isinstance(out.schema_observability, dict)
    assert out.schema_observability.get("schema_name") == "BrainOutput"
    assert out.schema_observability.get("schema_hash")


def test_turn_trace_includes_runtime_version_info(monkeypatch) -> None:
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._build_client", lambda: None)
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    trace = state.world_state[config.traces_key][-1]
    runtime_version = trace.get("runtime_version")
    assert isinstance(runtime_version, dict)
    assert "git_commit" in runtime_version


def test_context_precheck_mismatch_raises() -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state, context_id="baseline")
    config = build_conversacion_simple_pipeline_config(context_id="negociacion_sala_reuniones", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    with pytest.raises(RuntimeError):
        run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
