from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from conversacion_simple.nodes.brain_node import BrainOutput
from conversacion_simple.orchestration.pipeline import (
    SummarizerOutput,
    _call_brain_structured,
    _call_summarizer_structured,
    _normalize_schema_for_strict_json_schema,
)
from infra.openai.structured_outputs import validate_strict_json_schema
from infra.runtime_version import get_runtime_version_info


@dataclass
class Snapshot:
    name: str
    schema: dict[str, Any]


class _FakeBrainResponse:
    id = "resp_brain"
    output_text = (
        '{"schema_version":"brain.v1","status":"deliver","assistant_response":{"text":"ok"},'
        '"state_patch":{"conversation_state":{"phase":"desarrollo","status":"active","current_turn_goal":"goal"},'
        '"memory_working":{"current_topic":null,"pending_question":null,"last_turn_summary":"ok"},'
        '"memory_episodic_append":[]},"observability":{"rationale_summary":"ok"}}'
    )


class _FakeBrainResponses:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _FakeBrainResponse:
        self.kwargs = kwargs
        return _FakeBrainResponse()


class _FakeBrainClient:
    def __init__(self) -> None:
        self.responses = _FakeBrainResponses()


class _FakeSummarizerResponse:
    id = "resp_sum"
    output_text = (
        '{"schema_version":"memory_summary.v1","situation_live":"ok","active_proposal":null,'
        '"latest_offer_each_side":[],"concessions_accumulated":[],"open_items":[],"closed_items":[],'
        '"operative_constraints":[],"fixed_time_calculations":[],"operative_question_live":null,'
        '"sensitive_info_exposed":[],"agreement_progress":null,"pending_inconsistencies":[],"uncertainties":[]}'
    )


class _FakeSummarizerResponses:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _FakeSummarizerResponse:
        self.kwargs = kwargs
        return _FakeSummarizerResponse()


class _FakeSummarizerClient:
    def __init__(self) -> None:
        self.responses = _FakeSummarizerResponses()


def _schema_hash(schema: dict[str, Any]) -> str:
    payload = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def _object_nodes(schema: Any, path: str = "$") -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(schema, dict):
        props = schema.get("properties")
        req = schema.get("required")
        if isinstance(props, dict):
            prop_keys = list(props.keys())
            req_keys = req if isinstance(req, list) else []
            found.append(
                {
                    "path": path,
                    "properties": prop_keys,
                    "required": req_keys,
                    "missing": [k for k in prop_keys if k not in req_keys],
                    "extra": [k for k in req_keys if k not in prop_keys],
                    "additionalProperties": schema.get("additionalProperties"),
                }
            )
        for k, v in schema.items():
            child_path = f"{path}/{k}"
            found.extend(_object_nodes(v, child_path))
    elif isinstance(schema, list):
        for i, item in enumerate(schema):
            found.extend(_object_nodes(item, f"{path}[{i}]"))
    return found


def _summarize(snapshot: Snapshot) -> dict[str, Any]:
    report = validate_strict_json_schema(snapshot.schema)
    return {
        "name": snapshot.name,
        "hash": _schema_hash(snapshot.schema),
        "first_mismatch": report.get("first_mismatch"),
        "root_properties": list(snapshot.schema.get("properties", {}).keys()),
        "root_required": snapshot.schema.get("required", []),
        "brainstatepatch_properties": list(
            snapshot.schema.get("$defs", {}).get("BrainStatePatch", {}).get("properties", {}).keys()
        ),
        "brainstatepatch_required": snapshot.schema.get("$defs", {}).get("BrainStatePatch", {}).get("required", []),
    }


def main() -> None:
    runtime_version = get_runtime_version_info()

    base_brain = BrainOutput.model_json_schema()
    normalized_brain = _normalize_schema_for_strict_json_schema(deepcopy(base_brain))

    brain_client = _FakeBrainClient()
    _call_brain_structured(client=brain_client, model="gpt-5.4", messages=[])
    sent_brain = brain_client.responses.kwargs["text"]["format"]["schema"]

    base_sum = SummarizerOutput.model_json_schema()
    normalized_sum = _normalize_schema_for_strict_json_schema(deepcopy(base_sum))

    sum_client = _FakeSummarizerClient()
    _call_summarizer_structured(client=sum_client, model="gpt-5.4", messages=[])
    sent_sum = sum_client.responses.kwargs["text"]["format"]["schema"]

    synthetic_bad = deepcopy(sent_brain)
    synthetic_bad["required"] = list(synthetic_bad.get("required", [])) + ["memory_episodic_append"]

    result = {
        "runtime_version": runtime_version,
        "brain": {
            "name": brain_client.responses.kwargs["text"]["format"].get("name"),
            "strict": brain_client.responses.kwargs["text"]["format"].get("strict"),
            "base": _summarize(Snapshot("brain.base", base_brain)),
            "normalized": _summarize(Snapshot("brain.normalized", normalized_brain)),
            "sent": _summarize(Snapshot("brain.sent", sent_brain)),
        },
        "summarizer": {
            "name": sum_client.responses.kwargs["text"]["format"].get("name"),
            "strict": sum_client.responses.kwargs["text"]["format"].get("strict"),
            "base": _summarize(Snapshot("summarizer.base", base_sum)),
            "normalized": _summarize(Snapshot("summarizer.normalized", normalized_sum)),
            "sent": _summarize(Snapshot("summarizer.sent", sent_sum)),
        },
        "synthetic_error_alignment": {
            "expected_provider_error": "Extra required key 'memory_episodic_append' supplied",
            "first_mismatch": validate_strict_json_schema(synthetic_bad).get("first_mismatch"),
            "root_node": _object_nodes(synthetic_bad, "$")[0],
        },
    }

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
