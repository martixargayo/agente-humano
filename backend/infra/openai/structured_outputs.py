from __future__ import annotations


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
