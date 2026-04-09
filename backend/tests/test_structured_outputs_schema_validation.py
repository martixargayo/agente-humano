from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.nodes.brain_node import BrainOutput
from conversacion_simple.orchestration.pipeline import SummarizerOutput
from infra.openai.structured_outputs import (
    build_schema_observability,
    normalize_schema_for_strict_json_schema,
    validate_openai_structured_output_subset,
    validate_strict_json_schema,
)


def test_validate_strict_json_schema_detects_missing_and_extra_required_at_root() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        "required": ["a", "ghost"],
        "additionalProperties": False,
    }
    report = validate_strict_json_schema(schema)
    assert report["valid"] is False
    assert report["missing_required"] == [{"path": "$", "missing_keys": ["b"]}]
    assert report["extra_required"] == [{"path": "$", "extra_keys": ["ghost"]}]


def test_validate_strict_json_schema_detects_recursive_mismatch_in_defs() -> None:
    schema = {
        "type": "object",
        "properties": {"node": {"$ref": "#/$defs/Node"}},
        "required": ["node"],
        "additionalProperties": False,
        "$defs": {
            "Node": {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x", "y"],
                "additionalProperties": False,
            }
        },
    }
    report = validate_strict_json_schema(schema)
    assert report["valid"] is False
    assert report["extra_required"] == [{"path": "$/$defs/Node", "extra_keys": ["y"]}]


def test_validate_strict_json_schema_detects_additional_properties_violation() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
    }
    report = validate_strict_json_schema(schema)
    assert report["valid"] is False
    assert report["additional_properties_violations"] == [{"path": "$", "additionalProperties": None}]


def test_brainoutput_normalized_schema_is_strict_valid() -> None:
    normalized = normalize_schema_for_strict_json_schema(BrainOutput.model_json_schema())
    report = validate_strict_json_schema(normalized)
    assert report["valid"] is True


def test_summarizer_normalized_schema_is_strict_valid() -> None:
    normalized = normalize_schema_for_strict_json_schema(SummarizerOutput.model_json_schema())
    report = validate_strict_json_schema(normalized)
    assert report["valid"] is True


def test_schema_observability_includes_root_summary_and_first_mismatch() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["ghost"],
        "additionalProperties": False,
    }
    report = validate_strict_json_schema(schema)
    obs = build_schema_observability(schema_name="DemoSchema", schema=schema, validation_report=report)
    assert obs["schema_name"] == "DemoSchema"
    assert isinstance(obs["schema_hash"], str) and len(obs["schema_hash"]) == 16
    assert obs["root_properties"] == ["a"]
    assert obs["root_required"] == ["ghost"]
    assert obs["validation"]["first_mismatch"]["kind"] in {"missing_required", "extra_required"}


def test_validate_strict_json_schema_does_not_cover_openai_subset_root_anyof_limitation() -> None:
    schema = {
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
    report = validate_strict_json_schema(schema)
    # Nuestro validador local solo verifica invariantes strict internos.
    # No valida todas las restricciones del subconjunto OpenAI (ej: root anyOf).
    assert report["valid"] is True


def test_validate_openai_structured_output_subset_rejects_root_anyof() -> None:
    schema = {
        "anyOf": [
            {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"], "additionalProperties": False},
            {"type": "object", "properties": {"b": {"type": "string"}}, "required": ["b"], "additionalProperties": False},
        ]
    }
    report = validate_openai_structured_output_subset(schema)
    assert report["valid"] is False
    assert report["first_violation"]["kind"] in {"root_not_object", "root_anyof_not_supported"}


def test_validate_openai_structured_output_subset_detects_unsupported_keyword() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
        "additionalProperties": False,
        "allOf": [],
    }
    report = validate_openai_structured_output_subset(schema)
    assert report["valid"] is False
    assert report["first_violation"]["kind"] == "unsupported_keyword"
