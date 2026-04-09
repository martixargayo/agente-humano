from __future__ import annotations

import argparse
import copy
import json
import os
from typing import Any

from conversacion_simple.nodes.brain_node import BrainOutput
from infra.openai.structured_outputs import normalize_schema_for_strict_json_schema
from scripts.replay_structured_output_request import replay_raw_http


def _clean_titles(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _clean_titles(v) for k, v in node.items() if k != "title"}
    if isinstance(node, list):
        return [_clean_titles(v) for v in node]
    return node


def _clean_defaults(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _clean_defaults(v) for k, v in node.items() if k != "default"}
    if isinstance(node, list):
        return [_clean_defaults(v) for v in node]
    return node


def _inline_brainstatepatch(schema: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(schema)
    defs = out.get("$defs", {}) if isinstance(out.get("$defs"), dict) else {}
    bsp = defs.get("BrainStatePatch")
    props = out.get("properties")
    if isinstance(props, dict) and isinstance(bsp, dict) and isinstance(props.get("state_patch"), dict):
        props["state_patch"] = bsp
    if isinstance(out.get("$defs"), dict):
        out.pop("$defs", None)
    return out


def _minimal_root_state_patch(schema: dict[str, Any]) -> dict[str, Any]:
    out = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": schema.get("properties", {}).get("schema_version", {"const": "brain.v1", "type": "string"}),
            "state_patch": schema.get("properties", {}).get("state_patch", {}),
        },
        "required": ["schema_version", "state_patch"],
    }
    if isinstance(schema.get("$defs"), dict):
        out["$defs"] = schema["$defs"]
    return out


def _state_patch_memory_only(schema: dict[str, Any]) -> dict[str, Any]:
    out = _inline_brainstatepatch(schema)
    props = out.get("properties", {})
    state_patch = props.get("state_patch", {}) if isinstance(props, dict) else {}
    if isinstance(state_patch, dict):
        state_patch_props = state_patch.get("properties", {})
        if isinstance(state_patch_props, dict):
            state_patch["properties"] = {
                "memory_episodic_append": state_patch_props.get("memory_episodic_append", {"type": "array", "items": {"type": "string"}})
            }
            state_patch["required"] = ["memory_episodic_append"]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {"state_patch": state_patch},
        "required": ["state_patch"],
    }


def _variants(base_schema: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        ("v0_full_normalized", copy.deepcopy(base_schema)),
        ("v1_no_title", _clean_titles(base_schema)),
        ("v2_no_default", _clean_defaults(base_schema)),
        ("v3_inline_refs_remove_defs", _inline_brainstatepatch(base_schema)),
        ("v4_root_state_patch_only", _minimal_root_state_patch(base_schema)),
        ("v5_state_patch_memory_only", _state_patch_memory_only(base_schema)),
        ("v6_drop_observability", _drop_observability(base_schema)),
    ]


def _drop_observability(schema: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(schema)
    props = out.get("properties")
    req = out.get("required")
    if isinstance(props, dict):
        props.pop("observability", None)
    if isinstance(req, list):
        out["required"] = [x for x in req if x != "observability"]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Reduction campaign for BrainOutput schema against OpenAI")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required")

    base = normalize_schema_for_strict_json_schema(BrainOutput.model_json_schema())
    rows: list[dict[str, Any]] = []
    for name, schema in _variants(base):
        payload = {
            "model": args.model,
            "input": [{"role": "developer", "content": "Return JSON."}, {"role": "user", "content": "hola"}],
            "text": {"format": {"type": "json_schema", "name": "BrainOutput", "schema": schema, "strict": True}},
            "reasoning": {"effort": "low"},
            "store": False,
        }
        result = replay_raw_http(payload, api_key=api_key, base_url=args.base_url)
        rows.append(
            {
                "variant": name,
                "schema_hash": hash(json.dumps(schema, sort_keys=True, ensure_ascii=False)),
                "ok": result.get("ok"),
                "status_code": result.get("status_code"),
                "error_code": result.get("error_code"),
                "error_message": result.get("error_message"),
            }
        )
    print(json.dumps({"model": args.model, "variants": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
