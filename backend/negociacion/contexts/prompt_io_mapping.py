from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

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


class FieldMappingRuleV2(FieldMappingRule):
    value_aliases: dict[str, str] | None = None


class NodePromptIOMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, FieldMappingRule] = Field(default_factory=dict)
    outputs: dict[str, FieldMappingRule] = Field(default_factory=dict)


class NodePromptIOMappingV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, FieldMappingRuleV2] = Field(default_factory=dict)
    outputs: dict[str, FieldMappingRuleV2] = Field(default_factory=dict)


class PromptIOMappingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["prompt_io_mapping.v1"] = "prompt_io_mapping.v1"
    nodes: dict[NodeName, NodePromptIOMapping] = Field(default_factory=dict)


class PromptIOMappingConfigV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["prompt_io_mapping.v2"] = "prompt_io_mapping.v2"
    nodes: dict[NodeName, NodePromptIOMappingV2] = Field(default_factory=dict)


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
class _PathSegment:
    name: str
    is_array: bool


@dataclass(frozen=True)
class _CompiledRule:
    path: str
    parent_path: str
    key_name: str
    is_array_field: bool
    rule: FieldMappingRuleV2
    required_output: bool


@dataclass(frozen=True)
class _NodeCompiledV2:
    input_rules: dict[str, _CompiledRule]
    output_rules: dict[str, _CompiledRule]
    input_key_maps: dict[str, dict[str, str]]
    output_key_maps: dict[str, dict[str, str]]
    output_inverse_maps: dict[str, dict[str, str]]


@dataclass(frozen=True)
class PromptIOAdapter:
    config: PromptIOMappingConfig | PromptIOMappingConfigV2
    version: Literal["v1", "v2"] = "v1"
    compiled_v2: dict[NodeName, _NodeCompiledV2] | None = None

    @staticmethod
    def identity() -> "PromptIOAdapter":
        return PromptIOAdapter(config=PromptIOMappingConfig())

    def adapt_input_payload(self, node: NodeName, payload: dict[str, Any]) -> dict[str, Any]:
        if self.version == "v2":
            return self._adapt_input_payload_v2(node, payload)

        node_cfg = self.config.nodes.get(node)
        if node_cfg is None or not isinstance(node_cfg, NodePromptIOMapping):
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
        if self.version == "v2":
            return self._normalize_output_payload_v2(node, payload)

        node_cfg = self.config.nodes.get(node)
        if node_cfg is None or not isinstance(node_cfg, NodePromptIOMapping):
            return payload

        visible_to_canonical = _visible_to_canonical_output_map(node_cfg)
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            canonical_name = visible_to_canonical.get(key, key)
            normalized[canonical_name] = value
        return normalized

    def output_schema(self, node: NodeName, response_model: type[BaseModel]) -> dict[str, Any] | None:
        if self.version == "v2":
            return self._output_schema_v2(node, response_model)

        node_cfg = self.config.nodes.get(node)
        if node_cfg is None or not isinstance(node_cfg, NodePromptIOMapping):
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

    def _adapt_input_payload_v2(self, node: NodeName, payload: dict[str, Any]) -> dict[str, Any]:
        compiled = (self.compiled_v2 or {}).get(node)
        if compiled is None:
            return payload
        return _transform_object_canonical_to_visible(payload, "", compiled.input_rules, compiled.input_key_maps)

    def _normalize_output_payload_v2(self, node: NodeName, payload: dict[str, Any]) -> dict[str, Any]:
        compiled = (self.compiled_v2 or {}).get(node)
        if compiled is None:
            return payload
        return _transform_object_visible_to_canonical(payload, "", compiled.output_rules, compiled.output_inverse_maps)

    def _output_schema_v2(self, node: NodeName, response_model: type[BaseModel]) -> dict[str, Any] | None:
        compiled = (self.compiled_v2 or {}).get(node)
        if compiled is None:
            return None
        schema = response_model.model_json_schema()
        return _transform_schema_object_canonical_to_visible(schema, "", compiled.output_rules, compiled.output_key_maps)


def load_prompt_io_adapter(mapping_path: Path | None) -> PromptIOAdapter:
    if mapping_path is None:
        return PromptIOAdapter.identity()

    try:
        raw = json.loads(mapping_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PromptIOMappingError(f"prompt_io_mapping_load_error path={mapping_path} error={exc}") from exc

    schema_version = raw.get("schema_version") if isinstance(raw, dict) else None

    if schema_version == "prompt_io_mapping.v2":
        try:
            config_v2 = PromptIOMappingConfigV2.model_validate(raw)
        except ValidationError as exc:
            raise _schema_validation_error(mapping_path, exc) from exc
        compiled = _compile_v2_mapping(config_v2)
        return PromptIOAdapter(config=config_v2, version="v2", compiled_v2=compiled)

    try:
        config = PromptIOMappingConfig.model_validate(raw)
    except ValidationError as exc:
        raise _schema_validation_error(mapping_path, exc) from exc

    _validate_mapping(config)
    return PromptIOAdapter(config=config)


def _schema_validation_error(mapping_path: Path, exc: ValidationError) -> PromptIOMappingError:
    details: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", []))
        message = str(error.get("msg", "validation_error"))
        details.append(f"{location}:{message}")
    detail_text = "; ".join(details) if details else str(exc)
    return PromptIOMappingError(f"prompt_io_mapping_schema_invalid path={mapping_path} details={detail_text}")


def _compile_v2_mapping(config: PromptIOMappingConfigV2) -> dict[NodeName, _NodeCompiledV2]:
    compiled: dict[NodeName, _NodeCompiledV2] = {}
    input_models = _node_input_models()
    output_models = _node_output_models()

    for node, node_cfg in config.nodes.items():
        input_rules = _compile_rules_for_scope(node, "inputs", node_cfg.inputs, input_models[node], enforce_required_hide=False)
        output_rules = _compile_rules_for_scope(node, "outputs", node_cfg.outputs, output_models[node], enforce_required_hide=True)
        compiled[node] = _NodeCompiledV2(
            input_rules=input_rules,
            output_rules=output_rules,
            input_key_maps=_build_forward_maps(input_rules, output_scope=False),
            output_key_maps=_build_forward_maps(output_rules, output_scope=True),
            output_inverse_maps=_build_inverse_maps(output_rules),
        )
    return compiled


def _compile_rules_for_scope(
    node: NodeName,
    scope: Literal["inputs", "outputs"],
    rules: dict[str, FieldMappingRuleV2],
    model: type[BaseModel],
    *,
    enforce_required_hide: bool,
) -> dict[str, _CompiledRule]:
    schema = model.model_json_schema()
    compiled: dict[str, _CompiledRule] = {}

    for path, rule in rules.items():
        segments = _parse_path(path)
        parent = _render_path(segments[:-1]) if segments else ""
        last = segments[-1]
        path_meta = _resolve_path_in_schema(schema, segments)

        if rule.value_aliases:
            raise PromptIOMappingError(
                f"invalid_{scope[:-1]}_mapping node={node} path={path} rule=value_aliases reason=not_supported_in_v2_phase1"
            )

        if enforce_required_hide and not rule.should_expose() and path_meta["required"]:
            raise PromptIOMappingError(
                f"invalid_output_mapping node={node} path={path} rule=hide reason=cannot_hide_required_field"
            )

        compiled[path] = _CompiledRule(
            path=path,
            parent_path=parent,
            key_name=last.name,
            is_array_field=last.is_array,
            rule=rule,
            required_output=bool(path_meta["required"]),
        )

    _validate_parent_child_conflicts(node, scope, compiled)
    _validate_visible_collisions(node, scope, compiled)
    return compiled


def _validate_parent_child_conflicts(node: NodeName, scope: str, compiled: dict[str, _CompiledRule]) -> None:
    paths = sorted(compiled.keys(), key=len)
    for parent in paths:
        parent_rule = compiled[parent].rule
        if parent_rule.should_expose():
            continue
        prefix = f"{parent}."
        prefix_arr = f"{parent}[]."
        for child in paths:
            if child == parent:
                continue
            if child.startswith(prefix) or child.startswith(prefix_arr):
                raise PromptIOMappingError(
                    f"invalid_{scope[:-1]}_mapping node={node} path={child} rule=conflict reason=parent_hidden path_parent={parent}"
                )


def _validate_visible_collisions(node: NodeName, scope: str, compiled: dict[str, _CompiledRule]) -> None:
    by_parent: dict[str, set[str]] = {}
    for path, item in compiled.items():
        if not item.rule.should_expose():
            continue
        visible = _visible_output_name(item.key_name, item.rule) if scope == "outputs" else _visible_input_name(item.key_name, item.rule)
        bucket = by_parent.setdefault(item.parent_path, set())
        if visible in bucket:
            raise PromptIOMappingError(
                f"invalid_{scope[:-1]}_mapping node={node} path={path} rule=rename reason=duplicate_visible_name visible={visible} parent={item.parent_path or '<root>'}"
            )
        bucket.add(visible)


def _build_forward_maps(compiled: dict[str, _CompiledRule], *, output_scope: bool) -> dict[str, dict[str, str]]:
    maps: dict[str, dict[str, str]] = {}
    for item in compiled.values():
        if not item.rule.should_expose():
            continue
        visible = _visible_output_name(item.key_name, item.rule) if output_scope else _visible_input_name(item.key_name, item.rule)
        maps.setdefault(item.parent_path, {})[item.key_name] = visible
    return maps


def _build_inverse_maps(compiled: dict[str, _CompiledRule]) -> dict[str, dict[str, str]]:
    maps: dict[str, dict[str, str]] = {}
    for item in compiled.values():
        if not item.rule.should_expose():
            continue
        visible = _visible_output_name(item.key_name, item.rule)
        maps.setdefault(item.parent_path, {})[visible] = item.key_name
    return maps


def _transform_object_canonical_to_visible(
    payload: dict[str, Any],
    parent_path: str,
    rules: dict[str, _CompiledRule],
    forward_maps: dict[str, dict[str, str]],
) -> dict[str, Any]:
    adapted: dict[str, Any] = {}
    key_map = forward_maps.get(parent_path, {})

    for key, value in payload.items():
        child_path = f"{parent_path}.{key}" if parent_path else key
        array_child_path = f"{child_path}[]"
        effective_path = array_child_path if isinstance(value, list) and array_child_path in rules else child_path
        rule_obj = rules.get(effective_path)
        if rule_obj is not None and not rule_obj.rule.should_expose():
            continue

        visible_key = key_map.get(key, key)
        adapted[visible_key] = _transform_value_canonical_to_visible(value, effective_path, rules, forward_maps)
    return adapted


def _transform_value_canonical_to_visible(
    value: Any,
    path: str,
    rules: dict[str, _CompiledRule],
    forward_maps: dict[str, dict[str, str]],
) -> Any:
    if isinstance(value, dict):
        return _transform_object_canonical_to_visible(value, path, rules, forward_maps)
    if isinstance(value, list):
        item_path = path if path.endswith("[]") else f"{path}[]"
        return [_transform_value_canonical_to_visible(item, item_path, rules, forward_maps) for item in value]
    return value


def _transform_object_visible_to_canonical(
    payload: dict[str, Any],
    parent_path: str,
    rules: dict[str, _CompiledRule],
    inverse_maps: dict[str, dict[str, str]],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    inverse = inverse_maps.get(parent_path, {})

    for key, value in payload.items():
        canonical_key = inverse.get(key, key)
        child_path = f"{parent_path}.{canonical_key}" if parent_path else canonical_key
        array_child_path = f"{child_path}[]"
        effective_path = array_child_path if isinstance(value, list) and array_child_path in rules else child_path

        rule_obj = rules.get(effective_path)
        if rule_obj is not None and not rule_obj.rule.should_expose():
            continue

        normalized[canonical_key] = _transform_value_visible_to_canonical(value, effective_path, rules, inverse_maps)
    return normalized


def _transform_value_visible_to_canonical(
    value: Any,
    path: str,
    rules: dict[str, _CompiledRule],
    inverse_maps: dict[str, dict[str, str]],
) -> Any:
    if isinstance(value, dict):
        return _transform_object_visible_to_canonical(value, path, rules, inverse_maps)
    if isinstance(value, list):
        item_path = path if path.endswith("[]") else f"{path}[]"
        return [_transform_value_visible_to_canonical(item, item_path, rules, inverse_maps) for item in value]
    return value


def _transform_schema_object_canonical_to_visible(
    schema: dict[str, Any],
    parent_path: str,
    rules: dict[str, _CompiledRule],
    forward_maps: dict[str, dict[str, str]],
) -> dict[str, Any]:
    cloned = json.loads(json.dumps(schema))

    def _walk(node: dict[str, Any], current_path: str) -> dict[str, Any]:
        target = _schema_deref(node, cloned)

        if _schema_is_array(target):
            items = target.get("items")
            if isinstance(items, dict):
                _walk(items, f"{current_path}[]")
            return node

        properties = target.get("properties")
        if not isinstance(properties, dict):
            return node

        required = set(target.get("required", [])) if isinstance(target.get("required"), list) else set()
        key_map = forward_maps.get(current_path, {})

        new_props: dict[str, Any] = {}
        new_required: list[str] = []

        for canonical_key, prop_schema in properties.items():
            child_path = f"{current_path}.{canonical_key}" if current_path else canonical_key
            prop_target = _schema_deref(prop_schema, cloned)
            array_child_path = f"{child_path}[]"
            is_array = _schema_is_array(prop_target)
            effective_path = array_child_path if is_array and array_child_path in rules else child_path
            rule_obj = rules.get(effective_path)

            if rule_obj is not None and not rule_obj.rule.should_expose():
                continue

            visible_key = key_map.get(canonical_key, canonical_key)
            walked_prop = _walk(prop_schema, effective_path if is_array else child_path)
            new_props[visible_key] = walked_prop
            if canonical_key in required:
                new_required.append(visible_key)

        target["properties"] = new_props
        target["required"] = new_required
        return node

    return _walk(cloned, parent_path)


def _schema_deref(node: Any, root: dict[str, Any]) -> dict[str, Any]:
    current = node
    while isinstance(current, dict) and "$ref" in current:
        ref = current.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#/"):
            break
        parts = ref[2:].split("/")
        resolved: Any = root
        for part in parts:
            if not isinstance(resolved, dict):
                return current
            resolved = resolved.get(part)
        current = resolved
    return current if isinstance(current, dict) else {}


def _schema_is_array(node: dict[str, Any]) -> bool:
    if node.get("type") == "array":
        return True
    if isinstance(node.get("items"), dict):
        return True
    return False


def _resolve_path_in_schema(root_schema: dict[str, Any], segments: list[_PathSegment]) -> dict[str, Any]:
    current: dict[str, Any] = root_schema
    required = False

    for seg in segments:
        target = _schema_deref(current, root_schema)
        props = target.get("properties")
        if not isinstance(props, dict) or seg.name not in props:
            raise PromptIOMappingError(f"invalid_mapping_path path={_render_path(segments)} reason=field_not_found")

        required_set = set(target.get("required", [])) if isinstance(target.get("required"), list) else set()
        required = seg.name in required_set

        next_schema = _schema_deref(props[seg.name], root_schema)
        if seg.is_array:
            if not _schema_is_array(next_schema):
                raise PromptIOMappingError(
                    f"invalid_mapping_path path={_render_path(segments)} reason=array_not_expected"
                )
            items = next_schema.get("items")
            if not isinstance(items, dict):
                raise PromptIOMappingError(
                    f"invalid_mapping_path path={_render_path(segments)} reason=array_items_not_object"
                )
            current = items
        else:
            current = next_schema

    return {"required": required}


def _parse_path(path: str) -> list[_PathSegment]:
    normalized = path.strip()
    if not normalized:
        raise PromptIOMappingError("invalid_mapping_path path=<empty> reason=empty")

    segments: list[_PathSegment] = []
    for part in normalized.split("."):
        token = part.strip()
        if not token:
            raise PromptIOMappingError(f"invalid_mapping_path path={path} reason=empty_segment")
        if token.endswith("[]"):
            name = token[:-2].strip()
            if not name:
                raise PromptIOMappingError(f"invalid_mapping_path path={path} reason=invalid_array_segment")
            segments.append(_PathSegment(name=name, is_array=True))
        elif "[" in token or "]" in token:
            raise PromptIOMappingError(f"invalid_mapping_path path={path} reason=unsupported_array_syntax")
        else:
            segments.append(_PathSegment(name=token, is_array=False))
    return segments


def _render_path(segments: list[_PathSegment]) -> str:
    parts = []
    for seg in segments:
        parts.append(f"{seg.name}[]" if seg.is_array else seg.name)
    return ".".join(parts)


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
