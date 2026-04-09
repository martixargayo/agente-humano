from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import httpx
import openai

from conversacion_simple.nodes.brain_node import BrainOutput
from conversacion_simple.orchestration.pipeline import (
    SummarizerOutput,
    _call_brain_structured,
    _call_summarizer_structured,
)
from infra.openai.structured_outputs import (
    build_schema_observability,
    normalize_schema_for_strict_json_schema,
    validate_strict_json_schema,
)


@dataclass
class CapturedRequest:
    path: str
    body: dict[str, Any]


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def _capture_requests_with_mock_openai() -> tuple[list[CapturedRequest], dict[str, Any], openai.OpenAI]:
    captured: list[CapturedRequest] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        captured.append(CapturedRequest(path=request.url.path, body=body))
        # We intentionally emulate provider-side schema rejection to exercise the same error lane.
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Invalid schema for response_format 'BrainOutput': In context=(), 'required' is required to be supplied and to be an array including every key in properties. Extra required key 'memory_episodic_append' supplied.",
                    "type": "invalid_request_error",
                    "param": "text.format.schema",
                    "code": "invalid_json_schema",
                }
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = openai.OpenAI(api_key="test", base_url="https://api.openai.com/v1", http_client=http_client)

    brain_call = _call_brain_structured(
        client=client,
        model="gpt-5.4",
        messages=[
            {"role": "developer", "content": "test"},
            {"role": "user", "content": "hola"},
        ],
    )
    summarizer_call = _call_summarizer_structured(
        client=client,
        model="gpt-5.4-nano",
        messages=[
            {"role": "developer", "content": "test"},
            {"role": "user", "content": "hola"},
        ],
    )

    return captured, {
        "brain": brain_call,
        "summarizer": summarizer_call,
    }, client


def _force_sdk_request_capture(
    *,
    client: openai.OpenAI,
    payload: dict[str, Any],
    captured: list[CapturedRequest],
) -> dict[str, Any]:
    before = len(captured)
    try:
        client.responses.create(**payload)
    except Exception as exc:
        error = {"error_type": type(exc).__name__, "message": str(exc)}
    else:
        error = {"error_type": None, "message": None}
    after = len(captured)
    body = captured[-1].body if after > before else None
    return {"captured": after > before, "body": body, "error": error}


def _schema_artifacts(model: type[Any]) -> dict[str, Any]:
    base = model.model_json_schema()
    normalized = normalize_schema_for_strict_json_schema(base)
    validation = validate_strict_json_schema(normalized)
    observability = build_schema_observability(schema_name=model.__name__, schema=normalized, validation_report=validation)
    return {
        "base_schema": base,
        "base_schema_hash": _hash(base),
        "normalized_schema": normalized,
        "normalized_schema_hash": _hash(normalized),
        "validation": validation,
        "observability": observability,
    }


def _local_openai_subset_gap_examples() -> dict[str, Any]:
    root_anyof_schema = {
        "anyOf": [
            {
                "type": "object",
                "properties": {"kind": {"type": "string"}},
                "required": ["kind"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
                "additionalProperties": False,
            },
        ]
    }
    return {
        "root_anyof_schema": root_anyof_schema,
        "local_validation": validate_strict_json_schema(root_anyof_schema),
    }


def _raw_http_equivalence_check(brain_request: dict[str, Any]) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(400, json={"error": {"message": "invalid_json_schema", "code": "invalid_json_schema"}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.openai.com/v1") as client:
        response = client.post(
            "/responses",
            headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
            json=brain_request,
        )

    return {
        "status_code": response.status_code,
        "request_hash": _hash(brain_request),
        "serialized_hash": _hash(captured.get("body")),
        "equal": captured.get("body") == brain_request,
    }


def build_report() -> dict[str, Any]:
    brain_artifacts = _schema_artifacts(BrainOutput)
    summarizer_artifacts = _schema_artifacts(SummarizerOutput)

    captured_requests, calls, client = _capture_requests_with_mock_openai()

    brain_traced = calls["brain"].provider_request
    if not isinstance(brain_traced, dict):
        brain_traced = {
            "model": "gpt-5.4",
            "input": [
                {"role": "developer", "content": "test"},
                {"role": "user", "content": "hola"},
            ],
            "text": {"format": {"type": "json_schema", "name": "BrainOutput", "schema": brain_artifacts["normalized_schema"], "strict": True}},
            "reasoning": {"effort": "low"},
            "store": False,
        }
    brain_forced = _force_sdk_request_capture(client=client, payload=brain_traced, captured=captured_requests)
    brain_http = brain_forced["body"] if isinstance(brain_forced["body"], dict) else {}

    summarizer_traced = calls["summarizer"].provider_request
    if not isinstance(summarizer_traced, dict):
        summarizer_traced = {
            "model": "gpt-5.4-nano",
            "input": [
                {"role": "developer", "content": "test"},
                {"role": "user", "content": "hola"},
            ],
            "text": {"format": {"type": "json_schema", "name": "SummarizerOutput", "schema": summarizer_artifacts["normalized_schema"], "strict": True}},
            "reasoning": {"effort": "minimal"},
            "store": False,
        }
    summarizer_forced = _force_sdk_request_capture(client=client, payload=summarizer_traced, captured=captured_requests)
    summarizer_http = summarizer_forced["body"] if isinstance(summarizer_forced["body"], dict) else {}

    brain_schema_http = (((brain_http.get("text") or {}).get("format") or {}).get("schema"))
    brain_schema_traced = ((((brain_traced or {}).get("text") or {}).get("format") or {}).get("schema"))
    summarizer_schema_http = (((summarizer_http.get("text") or {}).get("format") or {}).get("schema"))
    summarizer_schema_traced = ((((summarizer_traced or {}).get("text") or {}).get("format") or {}).get("schema"))

    report = {
        "report_version": "structured_outputs_wire_capture.v1",
        "openai_sdk_version": openai.__version__,
        "brain": {
            **brain_artifacts,
            "provider_request_hash": _hash(brain_traced),
            "http_body_hash": _hash(brain_http),
            "schema_in_provider_request_hash": _hash(brain_schema_traced),
            "schema_in_http_body_hash": _hash(brain_schema_http),
            "provider_request_equals_http_body": brain_traced == brain_http,
            "schema_equals_normalized": brain_schema_http == brain_artifacts["normalized_schema"],
            "root_required_has_memory_episodic_append": "memory_episodic_append" in ((brain_schema_http or {}).get("required") or []),
            "brainstatepatch_required_has_memory_episodic_append": "memory_episodic_append" in ((((brain_schema_http or {}).get("$defs") or {}).get("BrainStatePatch") or {}).get("required") or []),
            "provider_error_code": calls["brain"].provider_exception.get("provider_exception_code") if calls["brain"].provider_exception else None,
            "provider_error_message": calls["brain"].provider_exception.get("provider_exception_message") if calls["brain"].provider_exception else None,
            "preflight_blocked": calls["brain"].fallback_reason_code == "schema_preflight_invalid",
            "forced_sdk_capture": brain_forced,
        },
        "summarizer": {
            **summarizer_artifacts,
            "provider_request_hash": _hash(summarizer_traced),
            "http_body_hash": _hash(summarizer_http),
            "schema_in_provider_request_hash": _hash(summarizer_schema_traced),
            "schema_in_http_body_hash": _hash(summarizer_schema_http),
            "provider_request_equals_http_body": summarizer_traced == summarizer_http,
            "schema_equals_normalized": summarizer_schema_http == summarizer_artifacts["normalized_schema"],
            "forced_sdk_capture": summarizer_forced,
        },
        "raw_http_equivalence": _raw_http_equivalence_check(brain_traced),
        "local_validator_gaps": _local_openai_subset_gap_examples(),
    }
    return report


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
