from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from negociacion.contexts import (
    bind_context_to_session,
    read_bound_context_from_session,
    resolve_negotiation_context,
)
from negociacion.contexts.prompt_io_mapping import PromptIOAdapter
from negociacion.orchestration import flow_config
from negociacion.orchestration.flow_config import (
    build_negotiation_pipeline_config,
    run_negotiation_cognitive_turn,
)
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.models import StructuredCallResult
from sessions.state import SessionState

REPORT_PATH = ROOT.parent / "docs" / "forensics_prompt_io_mapping_causality_report.json"

NODE_BY_SCHEMA = {
    "memory.v1": "memory",
    "phase_classifier.v1": "phase_classifier",
    "planner.v3": "planner",
    "executor.v1": "executor",
}

MARKERS = {
    "mustang": ["mustang", "vendedor", "papeles", "motor"],
    "sala": ["equipo a", "equipo b", "sala demo", "jueves"],
}


@dataclass
class AdapterLoadEvent:
    mapping_path: str | None
    mapping_hash: str | None
    adapter_id: int
    adapter_version: str
    node_count: int


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _marker_counts(text: str) -> dict[str, int]:
    lower = text.lower()
    return {name: sum(1 for token in tokens if token in lower) for name, tokens in MARKERS.items()}


def _flatten_keys(payload: Any, prefix: str = "") -> set[str]:
    out: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.add(path)
            out |= _flatten_keys(value, path)
    elif isinstance(payload, list):
        for idx, value in enumerate(payload):
            path = f"{prefix}[{idx}]"
            out |= _flatten_keys(value, path)
    return out


def _fake_call_structured(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    node_name: str,
    prompt_io_adapter: PromptIOAdapter,
    response_model: type[Any],
    reasoning_effort: str,
    request_context: dict[str, str],
    store: bool,
) -> StructuredCallResult:
    _ = (client, model, messages, node_name, prompt_io_adapter, reasoning_effort, request_context, store)
    if response_model.__name__ == "MemoryOutput":
        parsed = {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "diag", "pending_question": None, "last_turn_summary": "diag"},
            "negotiation_state": {
                "status": "active",
                "active_axes": ["precio"],
                "last_offer_self": None,
                "last_offer_other": None,
                "tentative_agreement": None,
                "stall_state": {
                    "is_hard_stalemate": False,
                    "stalemate_reason": None,
                    "self_ultimatum_active": False,
                    "self_ultimatum_summary": None,
                },
                "blockers": [],
                "next_open_loop": None,
            },
        }
    elif response_model.__name__ == "PhaseClassifierOutput":
        parsed = {"schema_version": "phase_classifier.v1", "current_phase": "clima_humano"}
    elif response_model.__name__ == "PlannerOutput":
        parsed = {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": "diag",
            "decision": "ask",
            "content_plan": {"must_include": ["claridad"], "must_avoid": ["ruido"]},
            "limits": {
                "max_sentences": 2,
                "max_questions": 1,
                "allow_topic_shift": False,
                "allow_personal_disclosure": False,
            },
            "memory_targets": [],
            "done_criteria": ["ok"],
        }
    else:
        parsed = {
            "schema_version": "executor.v1",
            "status": "deliver",
            "spoken_text": "ok",
            "memory_used": [],
            "refusal_reason": None,
        }
    return StructuredCallResult(
        parsed_json=parsed,
        refusal=None,
        parse_error=None,
        exception_error=None,
        response=None,
        source=StructuredCallSource.model,
        model_called=True,
        raw_output_text=json.dumps(parsed, ensure_ascii=False),
    )


def _run_probe(
    *,
    requested_context_id: str,
    bind_session_context_id: str | None,
    mapping_mode: str,
    scenario_id: str,
) -> dict[str, Any]:
    state = SessionState(user_id=f"u_{scenario_id}", session_id=f"s_{scenario_id}")
    if bind_session_context_id is not None:
        bind_context_to_session(state=state, context=resolve_negotiation_context(bind_session_context_id))

    config = build_negotiation_pipeline_config(context_id=requested_context_id)

    load_events: list[AdapterLoadEvent] = []
    mapping_transform_events: list[dict[str, Any]] = []
    frozen_nodes: dict[str, dict[str, Any]] = {}

    original_loader = flow_config.load_prompt_io_adapter
    original_adapt = flow_config._adapt_payload_json_for_prompt
    original_freeze = flow_config.freeze_prompt_artifacts

    def _patched_loader(mapping_path: Path | None) -> PromptIOAdapter:
        adapter = original_loader(mapping_path)
        path_str = str(mapping_path) if mapping_path is not None else None
        content_hash = None
        if mapping_path is not None and mapping_path.exists():
            content_hash = _sha_text(mapping_path.read_text(encoding="utf-8"))

        if mapping_mode == "disabled_identity":
            adapter = PromptIOAdapter.identity()

        node_count = len(adapter.config.nodes) if hasattr(adapter.config, "nodes") else 0
        load_events.append(
            AdapterLoadEvent(
                mapping_path=path_str,
                mapping_hash=content_hash,
                adapter_id=id(adapter),
                adapter_version=adapter.version,
                node_count=node_count,
            )
        )
        return adapter

    def _patched_adapt(adapter: PromptIOAdapter, node: str, payload_json: str) -> str:
        before_payload = json.loads(payload_json)
        before_keys = sorted(_flatten_keys(before_payload))
        adapted_json = original_adapt(adapter, node, payload_json)
        after_payload = json.loads(adapted_json)
        after_keys = sorted(_flatten_keys(after_payload))
        mapping_transform_events.append(
            {
                "node": node,
                "adapter_id": id(adapter),
                "adapter_version": adapter.version,
                "changed": before_payload != after_payload,
                "before_key_count": len(before_keys),
                "after_key_count": len(after_keys),
                "before_keys_sample": before_keys[:30],
                "after_keys_sample": after_keys[:30],
            }
        )
        return adapted_json

    def _patched_freeze(**kwargs: Any):
        frozen = original_freeze(**kwargs)
        node = NODE_BY_SCHEMA.get(str(kwargs.get("output_schema_version", "")), "unknown")
        payload_text = frozen.payload_json
        frozen_nodes[node] = {
            "payload_chars": len(payload_text),
            "payload_hash": _sha_text(payload_text),
            "payload_markers": _marker_counts(payload_text),
            "developer_prompt_chars": frozen.artifacts.developer_prompt_chars,
            "user_prompt_chars": frozen.artifacts.user_prompt_chars,
            "user_prompt_markers": _marker_counts(frozen.artifacts.user_prompt_rendered),
        }
        return frozen

    with (
        patch("negociacion.orchestration.flow_config.load_prompt_io_adapter", _patched_loader),
        patch("negociacion.orchestration.flow_config._adapt_payload_json_for_prompt", _patched_adapt),
        patch("negociacion.orchestration.flow_config.freeze_prompt_artifacts", _patched_freeze),
        patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured),
    ):
        _, updated = run_negotiation_cognitive_turn(state, "hola", config)

    bound = read_bound_context_from_session(updated)
    traces = updated.world_state.get("negotiation_canonical_traces", [])
    latest = traces[-1] if isinstance(traces, list) and traces else {}
    context_meta = latest.get("context_meta", {}) if isinstance(latest, dict) else {}

    return {
        "scenario_id": scenario_id,
        "requested_context_id": requested_context_id,
        "session_bound_context_id": bound.context_id if bound is not None else None,
        "mapping_mode": mapping_mode,
        "adapter_load_events": [event.__dict__ for event in load_events],
        "mapping_transform_events": mapping_transform_events,
        "node_prompt_stats": frozen_nodes,
        "trace_context_meta": context_meta,
    }


def _adapter_audit() -> dict[str, Any]:
    contexts = ["baseline_current", "validacion_multicontexto", "sala_reuniones"]
    rows: list[dict[str, Any]] = []
    for context_id in contexts:
        resolved = resolve_negotiation_context(context_id)
        adapters: list[PromptIOAdapter] = []
        for _ in range(3):
            adapters.append(flow_config.load_prompt_io_adapter(resolved.prompt_io_mapping_path))
        ids = [id(adapter) for adapter in adapters]
        rows.append(
            {
                "context_id": context_id,
                "mapping_path": str(resolved.prompt_io_mapping_path) if resolved.prompt_io_mapping_path else None,
                "mapping_hash": _sha_text(resolved.prompt_io_mapping_path.read_text(encoding="utf-8")) if resolved.prompt_io_mapping_path else None,
                "versions": [adapter.version for adapter in adapters],
                "adapter_ids": ids,
                "unique_adapter_instances": len(set(ids)),
                "node_counts": [len(adapter.config.nodes) for adapter in adapters],
            }
        )
    return {"rows": rows}


def _mapping_mutation_audit() -> dict[str, Any]:
    sala = resolve_negotiation_context("sala_reuniones")
    adapter = flow_config.load_prompt_io_adapter(sala.prompt_io_mapping_path)
    before = json.dumps(adapter.config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)

    payload = {
        "schema_version": "planner_input.v1",
        "negotiation_brief": {"contexto_de_mercado": {"valor_estimado": "x"}},
        "negotiation_state": {
            "last_offer_self": {"price_amount": 1, "currency": "EUR"},
            "last_offer_other": {"price_amount": 2, "currency": "EUR"},
            "tentative_agreement": {"price_amount": 3, "currency": "EUR"},
        },
    }

    for _ in range(5):
        _ = adapter.adapt_input_payload("planner", deepcopy(payload))
        _ = adapter.normalize_output_payload("executor", {"schema_version": "executor.v1", "status": "deliver", "spoken_text": "ok", "memory_used": [], "refusal_reason": None})

    after = json.dumps(adapter.config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return {
        "config_hash_before": _sha_text(before),
        "config_hash_after": _sha_text(after),
        "mutated": before != after,
    }


def build_report() -> dict[str, Any]:
    scenarios = [
        _run_probe(
            requested_context_id="sala_reuniones",
            bind_session_context_id="sala_reuniones",
            mapping_mode="enabled",
            scenario_id="clean_sala_enabled",
        ),
        _run_probe(
            requested_context_id="sala_reuniones",
            bind_session_context_id="sala_reuniones",
            mapping_mode="disabled_identity",
            scenario_id="clean_sala_mapping_off",
        ),
        _run_probe(
            requested_context_id="sala_reuniones",
            bind_session_context_id="validacion_multicontexto",
            mapping_mode="enabled",
            scenario_id="skew_sala_over_validacion_enabled",
        ),
        _run_probe(
            requested_context_id="sala_reuniones",
            bind_session_context_id="validacion_multicontexto",
            mapping_mode="disabled_identity",
            scenario_id="skew_sala_over_validacion_mapping_off",
        ),
        _run_probe(
            requested_context_id="validacion_multicontexto",
            bind_session_context_id="validacion_multicontexto",
            mapping_mode="enabled",
            scenario_id="clean_validacion_enabled",
        ),
    ]

    return {
        "report_version": "prompt_io_mapping_causality.v1",
        "adapter_audit": _adapter_audit(),
        "mapping_mutation_audit": _mapping_mutation_audit(),
        "scenarios": scenarios,
    }


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
