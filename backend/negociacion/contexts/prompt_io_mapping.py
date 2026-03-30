from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NodeName = Literal["memory", "phase_classifier", "planner", "executor"]


class PromptIOMappingError(RuntimeError):
    pass


class FieldMappingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rename: str | None = None
    output_alias: str | None = None
    expose: bool | None = None
    hide: bool = False
    optional: bool | None = None

    def should_expose(self) -> bool:
        if self.hide:
            return False
        if self.expose is None:
            return True
        return self.expose


class NodePromptIOMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, FieldMappingRule] = Field(default_factory=dict)
    outputs: dict[str, FieldMappingRule] = Field(default_factory=dict)


class PromptIOMappingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["prompt_io_mapping.v1"] = "prompt_io_mapping.v1"
    nodes: dict[NodeName, NodePromptIOMapping] = Field(default_factory=dict)


def _node_input_models() -> dict[NodeName, type[BaseModel]]:
    from ..nodes.executor_node import ExecutorInput
    from ..nodes.memory_node import MemoryInput
    from ..nodes.phase_classifier_node import PhaseClassifierInput
    from ..nodes.planner_node import PlannerInput

    return {
        "memory": MemoryInput,
        "phase_classifier": PhaseClassifierInput,
        "planner": PlannerInput,
        "executor": ExecutorInput,
    }


def _node_output_models() -> dict[NodeName, type[BaseModel]]:
    from ..nodes.executor_node import ExecutorOutput
    from ..nodes.memory_node import MemoryOutput
    from ..nodes.phase_classifier_node import PhaseClassifierOutput
    from ..nodes.planner_node import PlannerOutput

    return {
        "memory": MemoryOutput,
        "phase_classifier": PhaseClassifierOutput,
        "planner": PlannerOutput,
        "executor": ExecutorOutput,
    }


@dataclass(frozen=True)
class PromptIOAdapter:
    config: PromptIOMappingConfig

    @staticmethod
    def identity() -> "PromptIOAdapter":
        return PromptIOAdapter(config=PromptIOMappingConfig())

    def adapt_input_payload(self, node: NodeName, payload: dict[str, Any]) -> dict[str, Any]:
        node_cfg = self.config.nodes.get(node)
        if node_cfg is None:
            return payload

        adapted: dict[str, Any] = {}
        for canonical_name, value in payload.items():
            rule = node_cfg.inputs.get(canonical_name)
            if rule is not None and not rule.should_expose():
                continue
            visible_name = _visible_input_name(canonical_name, rule)
            adapted[visible_name] = value
        return adapted

    def normalize_output_payload(self, node: NodeName, payload: dict[str, Any]) -> dict[str, Any]:
        node_cfg = self.config.nodes.get(node)
        if node_cfg is None:
            return payload

        visible_to_canonical = _visible_to_canonical_output_map(node_cfg)
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            canonical_name = visible_to_canonical.get(key, key)
            normalized[canonical_name] = value
        return normalized

    def output_schema(self, node: NodeName, response_model: type[BaseModel]) -> dict[str, Any] | None:
        node_cfg = self.config.nodes.get(node)
        if node_cfg is None:
            return None

        schema = response_model.model_json_schema()
        props = schema.get("properties")
        if not isinstance(props, dict):
            return schema

        required_set = set(schema.get("required", [])) if isinstance(schema.get("required"), list) else set()

        adapted_properties: dict[str, Any] = {}
        adapted_required: list[str] = []

        for canonical_name, prop_schema in props.items():
            rule = node_cfg.outputs.get(canonical_name)
            if rule is not None and not rule.should_expose():
                if canonical_name in required_set:
                    raise PromptIOMappingError(
                        f"invalid_output_mapping node={node} field={canonical_name} cannot_hide_required_field"
                    )
                continue

            visible_name = _visible_output_name(canonical_name, rule)
            if visible_name in adapted_properties:
                raise PromptIOMappingError(
                    f"invalid_output_mapping node={node} duplicate_visible_output_name={visible_name}"
                )
            adapted_properties[visible_name] = prop_schema

            if canonical_name in required_set:
                if rule is not None and rule.optional is True:
                    raise PromptIOMappingError(
                        f"invalid_output_mapping node={node} field={canonical_name} cannot_mark_required_field_optional"
                    )
                adapted_required.append(visible_name)

        schema["properties"] = adapted_properties
        schema["required"] = adapted_required
        return schema


def load_prompt_io_adapter(mapping_path: Path | None) -> PromptIOAdapter:
    if mapping_path is None:
        return PromptIOAdapter.identity()

    try:
        raw = json.loads(mapping_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PromptIOMappingError(f"prompt_io_mapping_load_error path={mapping_path} error={exc}") from exc

    config = PromptIOMappingConfig.model_validate(raw)
    _validate_mapping(config)
    return PromptIOAdapter(config=config)


def _validate_mapping(config: PromptIOMappingConfig) -> None:
    input_models = _node_input_models()
    output_models = _node_output_models()
    for node, node_cfg in config.nodes.items():
        allowed_input_fields = set(input_models[node].model_fields.keys())
        allowed_output_fields = set(output_models[node].model_fields.keys())

        unknown_inputs = sorted(set(node_cfg.inputs.keys()) - allowed_input_fields)
        if unknown_inputs:
            raise PromptIOMappingError(f"invalid_input_mapping node={node} unknown_fields={unknown_inputs}")

        unknown_outputs = sorted(set(node_cfg.outputs.keys()) - allowed_output_fields)
        if unknown_outputs:
            raise PromptIOMappingError(f"invalid_output_mapping node={node} unknown_fields={unknown_outputs}")

        _validate_duplicate_visible_inputs(node, node_cfg)
        _validate_duplicate_visible_outputs(node, node_cfg)


def _validate_duplicate_visible_inputs(node: NodeName, node_cfg: NodePromptIOMapping) -> None:
    input_models = _node_input_models()
    visible_names: set[str] = set()
    for canonical_name in input_models[node].model_fields.keys():
        rule = node_cfg.inputs.get(canonical_name)
        if rule is not None and not rule.should_expose():
            continue
        visible_name = _visible_input_name(canonical_name, rule)
        if visible_name in visible_names:
            raise PromptIOMappingError(f"invalid_input_mapping node={node} duplicate_visible_input_name={visible_name}")
        visible_names.add(visible_name)


def _validate_duplicate_visible_outputs(node: NodeName, node_cfg: NodePromptIOMapping) -> None:
    output_models = _node_output_models()
    visible_names: set[str] = set()
    required_fields = _required_output_fields(node)
    for canonical_name in output_models[node].model_fields.keys():
        rule = node_cfg.outputs.get(canonical_name)
        if rule is not None and not rule.should_expose():
            if canonical_name in required_fields:
                raise PromptIOMappingError(
                    f"invalid_output_mapping node={node} field={canonical_name} cannot_hide_required_field"
                )
            continue
        visible_name = _visible_output_name(canonical_name, rule)
        if visible_name in visible_names:
            raise PromptIOMappingError(f"invalid_output_mapping node={node} duplicate_visible_output_name={visible_name}")
        visible_names.add(visible_name)


def _required_output_fields(node: NodeName) -> set[str]:
    schema = _node_output_models()[node].model_json_schema()
    required = schema.get("required")
    if isinstance(required, list):
        return {item for item in required if isinstance(item, str)}
    return set()


def _visible_input_name(canonical_name: str, rule: FieldMappingRule | None) -> str:
    if rule is None:
        return canonical_name
    if isinstance(rule.rename, str) and rule.rename.strip():
        return rule.rename.strip()
    return canonical_name


def _visible_output_name(canonical_name: str, rule: FieldMappingRule | None) -> str:
    if rule is None:
        return canonical_name
    if isinstance(rule.output_alias, str) and rule.output_alias.strip():
        return rule.output_alias.strip()
    if isinstance(rule.rename, str) and rule.rename.strip():
        return rule.rename.strip()
    return canonical_name


def _visible_to_canonical_output_map(node_cfg: NodePromptIOMapping) -> dict[str, str]:
    visible_to_canonical: dict[str, str] = {}
    for canonical_name, rule in node_cfg.outputs.items():
        if not rule.should_expose():
            continue
        visible_name = _visible_output_name(canonical_name, rule)
        visible_to_canonical[visible_name] = canonical_name
    return visible_to_canonical
