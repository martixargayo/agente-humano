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
    StructuredSummarizerCall,
    _call_brain_structured,
    _call_summarizer_structured,
    _normalize_schema_for_strict_json_schema,
    _sanitize_exception_message,
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

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
    trace = updated.world_state[config.traces_key][-1]
    assert "No pude completar la generación del turno" in reply
    assert trace["brain_fallback_reason_code"] == "validation_error_after_parse"


def test_legacy_response_text_payload_is_coerced(monkeypatch) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json={"response_text": "hola desde legacy"}, response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    trace = updated.world_state[config.traces_key][-1]
    assert "No pude completar la generación del turno" in reply
    assert trace["brain_fallback_reason_code"] == "validation_error_after_parse"


@pytest.mark.parametrize(
    ("payload", "expected_reply", "expected_topic", "expected_fallback"),
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
            False,
        ),
        ({"response_text": "legacy-response-text"}, None, None, True),
        ({"response": "legacy-response-string"}, None, None, True),
        (
            {
                "response": {"text": "legacy-response-object"},
                "memory_patch": {"current_topic": "topic-memory-patch"},
            },
            None,
            None,
            True,
        ),
        (
            {
                "assistant_response_text": "legacy-assistant-response-text",
                "memory_working_patch": {"current_topic": "topic-working-patch"},
            },
            None,
            None,
            True,
        ),
        (
            {
                "assistant": {"text": "legacy-assistant-object"},
                "state_patch": {"memory_episodic_append": []},
            },
            None,
            None,
            True,
        ),
        (
            {
                "reply": "legacy-reply",
                "response_text": "ignored-when-reply-present",
                "state_patch": {"conversation_state": {"phase": "opening"}},
                "memory_patch": {"current_topic": "topic-combined"},
            },
            None,
            None,
            True,
        ),
    ],
)
def test_brain_output_canonicalization_family_variants(
    monkeypatch, payload: dict, expected_reply: str | None, expected_topic: str | None, expected_fallback: bool
) -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=payload, response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
    canonical = updated.world_state[config.memory_key]

    if expected_fallback:
        trace = updated.world_state[config.traces_key][-1]
        assert "No pude completar la generación del turno" in reply
        assert trace["brain_fallback_reason_code"] == "validation_error_after_parse"
        return
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

    _ = expected_phase
    trace = updated.world_state[config.traces_key][-1]
    assert "No pude completar la generación del turno" in reply
    assert trace["brain_fallback_reason_code"] == "validation_error_after_parse"


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

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
    trace = updated.world_state[config.traces_key][-1]
    assert "No pude completar la generación del turno" in reply
    assert trace["brain_fallback_reason_code"] == "validation_error_after_parse"


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

    trace = updated.world_state[config.traces_key][-1]
    assert "No pude completar la generación del turno" in reply
    assert trace["brain_fallback_reason_code"] == "validation_error_after_parse"


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

    reply, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
    trace = updated.world_state[config.traces_key][-1]
    assert "No pude completar la generación del turno" in reply
    assert trace["brain_fallback_reason_code"] == "validation_error_after_parse"


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
    assert out.schema_observability.get("schema_hash")
    assert out.schema_observability.get("root_properties")
    assert out.schema_observability.get("root_required")
    brain_patch = out.schema_observability.get("brain_state_patch")
    assert isinstance(brain_patch, dict)
    assert "memory_episodic_append" in brain_patch.get("properties", [])
    assert "memory_episodic_append" in brain_patch.get("required", [])


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
    assert out.schema_observability.get("schema_hash")
    assert out.schema_observability.get("root_properties")
    assert out.schema_observability.get("root_required")


def test_brain_preflight_invalid_schema_short_circuits_before_provider(monkeypatch) -> None:
    called = {"count": 0}

    class _UnexpectedResponses:
        def create(self, **kwargs):
            called["count"] += 1
            return None

    class _UnexpectedClient:
        responses = _UnexpectedResponses()

    def _break_normalization(schema: object) -> object:
        normalized = _normalize_schema_for_strict_json_schema(schema)
        if isinstance(normalized, dict):
            normalized["required"] = list(normalized.get("required", [])) + ["memory_episodic_append"]
        return normalized

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._normalize_schema_for_strict_json_schema", _break_normalization)
    out = _call_brain_structured(client=_UnexpectedClient(), model="gpt-5.4", messages=[{"role": "user", "content": "x"}])

    assert out.source == "fallback"
    assert out.fallback_reason_code == "schema_preflight_invalid"
    assert called["count"] == 0
    assert out.schema_observability is not None
    assert out.schema_observability.get("validation", {}).get("first_mismatch", {}).get("kind") == "extra_required"


def test_summarizer_preflight_invalid_schema_short_circuits_before_provider(monkeypatch) -> None:
    called = {"count": 0}

    class _UnexpectedResponses:
        def create(self, **kwargs):
            called["count"] += 1
            return None

    class _UnexpectedClient:
        responses = _UnexpectedResponses()

    def _break_normalization(schema: object) -> object:
        normalized = _normalize_schema_for_strict_json_schema(schema)
        if isinstance(normalized, dict):
            normalized["required"] = list(normalized.get("required", [])) + ["ghost_field"]
        return normalized

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._normalize_schema_for_strict_json_schema", _break_normalization)
    out = _call_summarizer_structured(client=_UnexpectedClient(), model="gpt-5.4", messages=[{"role": "user", "content": "x"}])

    assert out.source == "fallback"
    assert out.fallback_reason_code == "schema_preflight_invalid"
    assert called["count"] == 0
    assert out.schema_observability is not None
    assert out.schema_observability.get("validation", {}).get("first_mismatch", {}).get("kind") == "extra_required"


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
    assert out.fallback_reason_code == "provider_exception"
    assert out.model_attempted is True
    assert out.model_succeeded is False
    provider_exc = out.provider_exception
    assert isinstance(provider_exc, dict)
    assert provider_exc["provider_exception_type"] == "RuntimeError"
    assert provider_exc["provider_exception_stage"] == "brain"
    assert provider_exc["provider_model_target"] == "gpt-5-nano"
    assert provider_exc["provider_exception_status_code"] == 400
    assert provider_exc["provider_exception_code"] == "invalid_json_schema"
    assert "invalid schema" in str(provider_exc["provider_exception_message"]).lower()


def test_exception_message_sanitizer_redacts_credentials_and_truncates() -> None:
    raw = (
        "Authorization: Bearer sk-super-secret-token "
        "api_key=sk-super-secret-token "
        "access_token=abc123456789 "
        + ("x" * 1200)
    )
    sanitized = _sanitize_exception_message(raw, max_len=180)
    assert isinstance(sanitized, str)
    assert "super-secret-token" not in sanitized
    assert "abc123456789" not in sanitized
    assert "authorization: [redacted]" in sanitized.lower()
    assert sanitized.endswith("…[truncated]")


def test_provider_exception_observability_is_propagated_without_secret_leaks(monkeypatch) -> None:
    secret = "sk-top-secret-1234567890"

    class _SecretFailingResponses:
        def create(self, **kwargs):
            raise RuntimeError(f"Authorization: Bearer {secret}; code=rate_limit_exceeded")

    class _SecretFailingClient:
        responses = _SecretFailingResponses()

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._build_client", lambda: _SecretFailingClient())
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    _, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
    trace = updated.world_state[config.traces_key][-1]
    provider_exc = trace["memory_observability"]["brain_provider_exception"]
    node_summary = trace["nodes"]["brain"]["output_summary"]
    assert trace["brain_fallback_reason_code"] == "provider_exception"
    assert provider_exc["provider_exception_type"] == "RuntimeError"
    assert provider_exc["provider_exception_stage"] == "brain"
    assert provider_exc["provider_model_target"] == config.brain_model_target
    assert secret not in str(provider_exc["provider_exception_message"])
    assert node_summary["provider_exception_present"] is True
    assert "provider_exception" not in node_summary


def test_summarizer_provider_exception_observability_is_captured(monkeypatch) -> None:
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._build_client", lambda: object())

    def _fake_brain(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output(), response=None, model_attempted=True, model_succeeded=True)

    def _fake_summarizer(**kwargs):
        return StructuredSummarizerCall(
            source="fallback",
            output=None,
            response_id="sum-1",
            fallback_reason_code="provider_exception",
            model_attempted=True,
            model_succeeded=False,
            provider_exception={
                "provider_exception_type": "APIStatusError",
                "provider_exception_message": "Error code: 503 service unavailable",
                "provider_exception_status_code": 503,
                "provider_exception_code": "service_unavailable",
                "provider_exception_stage": "summarizer",
                "provider_model_target": "gpt-5.4-nano",
            },
        )

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    for i in range(21):
        run_conversacion_simple_turn(state=state, user_message=f"turno {i}", config=config, turn_context=turn_context)

    trace = state.world_state[config.traces_key][-1]
    obs = trace["memory_observability"]
    assert trace["brain_model_succeeded"] is True
    assert trace["brain_fallback_reason_code"] is None
    assert obs["memory_summary_compaction_source"] == "deterministic_fallback"
    assert obs["summarizer_fallback_reason_code"] == "provider_exception"
    assert obs["summarizer_provider_exception"]["provider_exception_stage"] == "summarizer"
    assert obs["summarizer_provider_exception"]["provider_exception_status_code"] == 503


def test_summarizer_heavy_observability_is_opt_in_forensic(monkeypatch) -> None:
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._build_client", lambda: object())

    def _fake_brain(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output(), response=None, model_attempted=True, model_succeeded=True)

    def _fake_summarizer(**kwargs):
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(
                schema_version="memory_summary.v1",
                situation_live="ok",
            ),
            response_id="sum-optin",
            model_attempted=True,
            model_succeeded=True,
            provider_request={"model": "gpt-5.4-nano", "input": []},
            provider_response_text='{"schema_version":"memory_summary.v1","situation_live":"ok"}',
            schema_observability={
                "schema_name": "SummarizerOutput",
                "schema_hash": "abc123",
                "root_properties": ["schema_version", "situation_live"],
                "validation": {"valid": True, "first_mismatch": None},
                "openai_subset_validation": {"valid": True, "first_violation": None},
            },
        )

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    monkeypatch.delenv("CONVERSACION_SIMPLE_TRACE_FORENSIC", raising=False)
    for i in range(21):
        run_conversacion_simple_turn(state=state, user_message=f"turno normal {i}", config=config, turn_context=turn_context)
    normal_obs = state.world_state[config.traces_key][-1]["memory_observability"]
    assert "summarizer_provider_request" not in normal_obs
    assert "summarizer_provider_response_text" not in normal_obs
    assert "schema_serialized" not in normal_obs["summarizer_runtime_fingerprint"]

    state_f = SessionState(user_id="uf", session_id="sf")
    _bind(state_f)
    turn_context_f = build_conversacion_simple_turn_context(state=state_f, entrypoint="/tests", requested_context_id="baseline")
    monkeypatch.setenv("CONVERSACION_SIMPLE_TRACE_FORENSIC", "1")
    for i in range(21):
        run_conversacion_simple_turn(state=state_f, user_message=f"turno forense {i}", config=config, turn_context=turn_context_f)
    forensic_obs = state_f.world_state[config.traces_key][-1]["memory_observability"]
    assert isinstance(forensic_obs.get("summarizer_provider_request"), dict)
    assert isinstance(forensic_obs.get("summarizer_provider_response_text"), str)
    assert "schema_serialized" in forensic_obs["summarizer_runtime_fingerprint"]


def test_structured_call_fallback_reason_codes_for_empty_and_parse_error() -> None:
    class _EmptyResponse:
        id = "resp_empty"
        output_text = ""

    class _BadJsonResponse:
        id = "resp_bad_json"
        output_text = "{not-json"

    class _EmptyResponses:
        def create(self, **kwargs):
            return _EmptyResponse()

    class _BadJsonResponses:
        def create(self, **kwargs):
            return _BadJsonResponse()

    class _EmptyClient:
        responses = _EmptyResponses()

    class _BadJsonClient:
        responses = _BadJsonResponses()

    empty = _call_brain_structured(
        client=_EmptyClient(),
        model="gpt-5-nano",
        messages=[{"role": "developer", "content": "prompt"}, {"role": "user", "content": "payload"}],
    )
    bad_json = _call_brain_structured(
        client=_BadJsonClient(),
        model="gpt-5-nano",
        messages=[{"role": "developer", "content": "prompt"}, {"role": "user", "content": "payload"}],
    )

    assert empty.source == "fallback"
    assert empty.fallback_reason_code == "empty_output_text"
    assert empty.model_attempted is True
    assert empty.model_succeeded is False
    assert bad_json.source == "fallback"
    assert bad_json.fallback_reason_code == "json_parse_error"
    assert bad_json.model_attempted is True
    assert bad_json.model_succeeded is False


def test_fallback_observability_and_social_ux_for_trivial_turns(monkeypatch) -> None:
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._build_client", lambda: None)
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply_hola, updated, _ = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
    trace_hola = updated.world_state[config.traces_key][-1]
    brain_hola = trace_hola["nodes"]["brain"]
    assert "No pude completar la generación del turno" in reply_hola
    assert trace_hola["brain_fallback_reason_code"] == "client_unavailable"
    assert trace_hola["brain_model_attempted"] is False
    assert trace_hola["brain_model_succeeded"] is False
    assert brain_hola["fallback_reason_code"] == "client_unavailable"
    assert brain_hola["model_attempted"] is False
    assert brain_hola["model_succeeded"] is False
    assert brain_hola["model_called"] is False
    assert trace_hola["memory_observability"]["brain_fallback_reason_code"] == "client_unavailable"

    reply_identity, updated, _ = run_conversacion_simple_turn(
        state=state,
        user_message="¿Cómo te llamas?",
        config=config,
        turn_context=turn_context,
    )
    assert "No pude completar la generación del turno" in reply_identity


def test_fallback_non_trivial_turn_keeps_prudent_response(monkeypatch) -> None:
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._build_client", lambda: None)
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, _ = run_conversacion_simple_turn(
        state=state,
        user_message="Necesito cerrar el reparto de horas para el jueves",
        config=config,
        turn_context=turn_context,
    )
    trace = updated.world_state[config.traces_key][-1]
    assert "No pude completar la generación del turno" in reply
    assert trace["final_reply_text"] == reply
    assert trace["brain_fallback_reason_code"] == "client_unavailable"


def test_fallback_reason_validation_error_after_parse(monkeypatch) -> None:
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._build_client", lambda: object())

    def _fake_call(**kwargs):
        return StructuredBrainCall(
            source="fallback",
            parsed_json={"schema_version": "brain.v1", "status": "deliver"},
            response=None,
            fallback_reason_code="json_parse_error",
            model_attempted=True,
            model_succeeded=False,
        )

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)

    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    reply, updated, meta = run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    trace = updated.world_state[config.traces_key][-1]
    brain = trace["nodes"]["brain"]
    assert reply
    assert meta["pipeline_topology"] == "single_llm"
    assert trace["brain_fallback_reason_code"] == "validation_error_after_parse"
    assert brain["fallback_reason_code"] == "validation_error_after_parse"
    assert brain["model_attempted"] is True
    assert brain["model_succeeded"] is False


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


def test_runtime_version_prefers_environment_metadata(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "commit-env-123")
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "branch-env")
    monkeypatch.setenv("RAILWAY_BUILD_ID", "build-env")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("SERVICE_VERSION", "svc-v1")
    from infra.runtime_version import get_runtime_version_info

    get_runtime_version_info.cache_clear()
    runtime = get_runtime_version_info()
    assert runtime["git_commit"] == "commit-env-123"
    assert runtime["git_branch"] == "branch-env"
    assert runtime["build_id"] == "build-env"
    assert runtime["deploy_env"] == "production"
    assert runtime["service_version"] == "svc-v1"


def test_context_precheck_mismatch_raises() -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state, context_id="baseline")
    config = build_conversacion_simple_pipeline_config(context_id="negociacion_sala_reuniones", stateful=True)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")

    with pytest.raises(RuntimeError):
        run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)
