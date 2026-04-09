from __future__ import annotations

import hashlib
import json
from typing import Any

def normalize_schema_for_strict_json_schema(schema: object) -> object:
    """Normalize JSON Schema for OpenAI Structured Outputs strict mode.

    For every object node that declares `properties`, strict mode expects
    `required` to exist and include all property keys.
    """

    if isinstance(schema, dict):
        normalized = {key: normalize_schema_for_strict_json_schema(value) for key, value in schema.items()}
        properties = normalized.get("properties")
        if isinstance(properties, dict):
            normalized["required"] = list(properties.keys())
        return normalized
    if isinstance(schema, list):
        return [normalize_schema_for_strict_json_schema(item) for item in schema]
    return schema


def _json_path(parts: tuple[str, ...]) -> str:
    if not parts:
        return "$"
    return "$/" + "/".join(parts)


def _extract_object_snapshot(node: object, *, max_keys: int = 20) -> dict[str, object] | None:
    if not isinstance(node, dict):
        return None
    properties = node.get("properties")
    required = node.get("required")
    if not isinstance(properties, dict):
        return None
    return {
        "properties": list(properties.keys())[:max_keys],
        "required": [str(item) for item in required][:max_keys] if isinstance(required, list) else [],
        "additionalProperties": node.get("additionalProperties"),
    }


def validate_strict_json_schema(schema: object) -> dict[str, Any]:
    """Validate strict JSON schema invariants used by OpenAI structured outputs."""

    missing_required: list[dict[str, Any]] = []
    extra_required: list[dict[str, Any]] = []
    additional_properties_violations: list[dict[str, Any]] = []

    def _walk(node: object, path: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            required = node.get("required")
            if isinstance(properties, dict):
                property_keys = list(properties.keys())
                required_items = required if isinstance(required, list) else []
                missing = [key for key in property_keys if key not in required_items]
                extra = [key for key in required_items if key not in property_keys]
                if missing:
                    missing_required.append({"path": _json_path(path), "missing_keys": missing})
                if extra:
                    extra_required.append({"path": _json_path(path), "extra_keys": extra})
                if node.get("additionalProperties") is not False:
                    additional_properties_violations.append(
                        {
                            "path": _json_path(path),
                            "additionalProperties": node.get("additionalProperties"),
                        }
                    )
            for key, value in node.items():
                _walk(value, (*path, key))
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                _walk(value, (*path, f"[{idx}]"))

    _walk(schema, tuple())
    first_mismatch = None
    if missing_required:
        first_mismatch = {"kind": "missing_required", **missing_required[0]}
    elif extra_required:
        first_mismatch = {"kind": "extra_required", **extra_required[0]}
    elif additional_properties_violations:
        first_mismatch = {"kind": "additional_properties", **additional_properties_violations[0]}

    return {
        "valid": not (missing_required or extra_required or additional_properties_violations),
        "missing_required": missing_required,
        "extra_required": extra_required,
        "additional_properties_violations": additional_properties_violations,
        "first_mismatch": first_mismatch,
    }


_OPENAI_UNSUPPORTED_KEYWORDS = {
    "allOf",
    "not",
    "if",
    "then",
    "else",
    "dependentRequired",
    "dependentSchemas",
    "patternProperties",
}


def validate_openai_structured_output_subset(schema: object) -> dict[str, Any]:
    """Best-effort validator for OpenAI Structured Outputs subset rules."""

    violations: list[dict[str, Any]] = []

    def _walk(node: object, path: tuple[str, ...], *, is_root: bool = False) -> None:
        if isinstance(node, dict):
            if is_root:
                node_type = node.get("type")
                if node_type != "object":
                    violations.append({"path": _json_path(path), "kind": "root_not_object", "value": node_type})
                if "anyOf" in node:
                    violations.append({"path": _json_path(path), "kind": "root_anyof_not_supported"})
            for keyword in _OPENAI_UNSUPPORTED_KEYWORDS:
                if keyword in node:
                    violations.append({"path": _json_path(path), "kind": "unsupported_keyword", "keyword": keyword})
            for key, value in node.items():
                _walk(value, (*path, key), is_root=False)
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                _walk(value, (*path, f"[{idx}]"), is_root=False)

    _walk(schema, tuple(), is_root=True)
    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "first_violation": violations[0] if violations else None,
    }


def build_schema_observability(*, schema_name: str, schema: object, validation_report: dict[str, Any], max_keys: int = 20) -> dict[str, Any]:
    serialized = json.dumps(schema, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    schema_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    root_properties: list[str] = []
    root_required: list[str] = []
    if isinstance(schema, dict):
        props = schema.get("properties")
        req = schema.get("required")
        if isinstance(props, dict):
            root_properties = list(props.keys())[:max_keys]
        if isinstance(req, list):
            root_required = [str(item) for item in req][:max_keys]
    brain_state_patch: dict[str, object] | None = None
    if isinstance(schema, dict):
        brain_state_patch = _extract_object_snapshot(schema.get("$defs", {}).get("BrainStatePatch"), max_keys=max_keys)
    return {
        "schema_name": schema_name,
        "schema_hash": schema_hash,
        "root_properties": root_properties,
        "root_required": root_required,
        "brain_state_patch": brain_state_patch,
        "validation": validation_report,
    }
