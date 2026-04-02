from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from negociacion.contexts import resolve_negotiation_context
from negociacion.orchestration import flow_config
from negociacion.orchestration.flow_config import (  # type: ignore
    NegotiationTurnConfig,
    build_negotiation_pipeline_config,
    run_negotiation_cognitive_turn,
)
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.models import StructuredCallResult
from sessions.state import SessionState

REPORT_PATH = ROOT.parent / "docs" / "forensics_multicontext_silent_collapse_report.json"

NODE_BY_SCHEMA = {
    "memory.v1": "memory",
    "phase_classifier.v1": "phase_classifier",
    "planner.v3": "planner",
    "executor.v1": "executor",
}

CONTEXT_MARKERS = {
    "validacion_multicontexto": ["mustang", "vendedor", "motor", "papeles"],
    "sala_reuniones": ["equipo a", "equipo b", "sala demo", "jueves"],
    "baseline_current": ["carlos", "negociación"],
}


@dataclass
class TurnProbe:
    requested_context_id: str
    session_id: str
    turn_idx: int
    node_payloads: dict[str, dict[str, Any]]
    node_artifacts: dict[str, dict[str, Any]]
    resolved_assets: dict[str, list[dict[str, Any]]]
    mapping_path: str | None
    trace_context_meta: dict[str, Any]
    fallbacks: list[str]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _contains_markers(payload_text: str) -> dict[str, int]:
    lower = payload_text.lower()
    out: dict[str, int] = {}
    for context_id, markers in CONTEXT_MARKERS.items():
        out[context_id] = sum(1 for marker in markers if marker in lower)
    return out


def _fake_call_structured(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    node_name: str,
    prompt_io_adapter: Any,
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
            "working_memory_new": {
                "current_topic": "diagnostico",
                "pending_question": None,
                "last_turn_summary": "forensics",
            },
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
            "turn_goal": "diagnosticar",
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
            "spoken_text": "Diagnóstico recibido.",
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


def _run_turn_probe(*, context_id: str, state: SessionState, turn_idx: int) -> TurnProbe:
    node_payloads: dict[str, dict[str, Any]] = {}
    node_artifacts: dict[str, dict[str, Any]] = {}
    resolved_assets: dict[str, list[dict[str, Any]]] = {"phase_classifier_card": [], "phase_cards": []}
    mapping_paths: list[str | None] = []

    original_freeze = flow_config.freeze_prompt_artifacts
    original_mapping_loader = flow_config.load_prompt_io_adapter
    original_load_phase_classifier_card = flow_config._load_phase_classifier_card
    original_load_phase_cards = flow_config._load_phase_cards

    def _patched_freeze(**kwargs: Any):
        frozen = original_freeze(**kwargs)
        node = NODE_BY_SCHEMA.get(str(kwargs.get("output_schema_version", "")), "unknown")
        payload = json.loads(frozen.payload_json)
        node_payloads[node] = {
            "payload": payload,
            "payload_hash": _sha(frozen.payload_json),
            "payload_chars": len(frozen.payload_json),
            "payload_tokens_est": int(len(frozen.payload_json) / 4),
            "markers": _contains_markers(frozen.payload_json),
            "object_ids": {
                "root": id(payload),
                "persona_policy": id(payload.get("persona_policy")) if isinstance(payload, dict) else None,
                "negotiation_brief": id(payload.get("negotiation_brief")) if isinstance(payload, dict) else None,
                "phase_card": id(payload.get("phase_card")) if isinstance(payload, dict) else None,
                "phase_classifier_card": id(payload.get("phase_classifier_card")) if isinstance(payload, dict) else None,
            },
        }
        node_artifacts[node] = {
            "developer_prompt_chars": frozen.artifacts.developer_prompt_chars,
            "user_prompt_chars": frozen.artifacts.user_prompt_chars,
            "payload_chars": frozen.artifacts.payload_chars,
            "payload_hash": frozen.artifacts.payload_hash,
            "user_prompt_hash": frozen.artifacts.user_prompt_hash,
            "markers_user_prompt": _contains_markers(frozen.artifacts.user_prompt_rendered),
            "user_prompt_tokens_est": int((frozen.artifacts.user_prompt_chars or 0) / 4),
        }
        return frozen

    def _patched_mapping_loader(mapping_path: Path | None):
        mapping_paths.append(str(mapping_path) if mapping_path is not None else None)
        return original_mapping_loader(mapping_path)

    def _patched_load_phase_classifier_card(prompts_dir: str):
        payload, source = original_load_phase_classifier_card(prompts_dir)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        resolved_assets["phase_classifier_card"].append(
            {
                "source": source,
                "hash": _sha(raw),
                "chars": len(raw),
                "markers": _contains_markers(raw),
            }
        )
        return payload, source

    def _patched_load_phase_cards(prompts_dir: str):
        cards = original_load_phase_cards(prompts_dir)
        dumped = {k.value: v.model_dump(mode="json") for k, v in cards.items()}
        raw = json.dumps(dumped, ensure_ascii=False, sort_keys=True)
        resolved_assets["phase_cards"].append(
            {
                "source": str(flow_config._resolve_context_asset_path(prompts_dir, asset_name="phase_cards")),
                "hash": _sha(raw),
                "chars": len(raw),
                "markers": _contains_markers(raw),
            }
        )
        return cards

    config: NegotiationTurnConfig = build_negotiation_pipeline_config(context_id=context_id)
    with (
        patch("negociacion.orchestration.flow_config.freeze_prompt_artifacts", _patched_freeze),
        patch("negociacion.orchestration.flow_config.load_prompt_io_adapter", _patched_mapping_loader),
        patch("negociacion.orchestration.flow_config._load_phase_classifier_card", _patched_load_phase_classifier_card),
        patch("negociacion.orchestration.flow_config._load_phase_cards", _patched_load_phase_cards),
        patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured),
    ):
        _, updated = run_negotiation_cognitive_turn(state, f"hola turno {turn_idx} contexto {context_id}", config)

    traces = updated.world_state.get("negotiation_canonical_traces", [])
    trace = traces[-1] if isinstance(traces, list) and traces else {}
    return TurnProbe(
        requested_context_id=context_id,
        session_id=state.session_id,
        turn_idx=turn_idx,
        node_payloads=node_payloads,
        node_artifacts=node_artifacts,
        resolved_assets=resolved_assets,
        mapping_path=mapping_paths[-1] if mapping_paths else None,
        trace_context_meta=trace.get("context_meta", {}) if isinstance(trace, dict) else {},
        fallbacks=trace.get("trace", {}).get("last_fallbacks", []) if isinstance(trace, dict) else [],
    )


def _asset_hash_snapshot() -> dict[str, dict[str, str]]:
    snapshots: dict[str, dict[str, str]] = {}
    for context_id in ["baseline_current", "validacion_multicontexto", "sala_reuniones"]:
        resolved = resolve_negotiation_context(context_id)
        snapshots[context_id] = {}
        for name, path in {
            "persona": resolved.persona_path,
            "negotiation_brief": resolved.negotiation_brief_path,
            "phase_cards": resolved.phase_cards_path,
            "phase_classifier_card": resolved.phase_classifier_card_path,
            "planner_prompt": resolved.prompts_dir / "planner_prompt.txt",
            "executor_prompt": resolved.prompts_dir / "executor_prompt.txt",
            "phase_classifier_prompt": resolved.prompts_dir / "phase_classifier_prompt.txt",
            "memory_prompt": resolved.prompts_dir / "summarizer_prompt.txt",
        }.items():
            text = path.read_text(encoding="utf-8")
            snapshots[context_id][name] = _sha(text)
    return snapshots


def _scenario_sequences() -> list[tuple[str, list[str]]]:
    return [
        ("only_validacion", ["validacion_multicontexto"]),
        ("only_sala", ["sala_reuniones"]),
        ("validacion_then_sala", ["validacion_multicontexto", "sala_reuniones"]),
        ("sala_then_validacion", ["sala_reuniones", "validacion_multicontexto"]),
        (
            "alternating",
            [
                "validacion_multicontexto",
                "sala_reuniones",
                "validacion_multicontexto",
                "sala_reuniones",
            ],
        ),
    ]


def build_report() -> dict[str, Any]:
    before = _asset_hash_snapshot()

    scenarios: dict[str, Any] = {}
    for scenario_name, sequence in _scenario_sequences():
        state = SessionState(user_id=f"u_{scenario_name}", session_id=f"s_{scenario_name}")
        turns: list[dict[str, Any]] = []
        for idx, context_id in enumerate(sequence, start=1):
            probe = _run_turn_probe(context_id=context_id, state=state, turn_idx=idx)
            turns.append(
                {
                    "requested_context_id": probe.requested_context_id,
                    "turn_idx": probe.turn_idx,
                    "mapping_path": probe.mapping_path,
                    "trace_context_meta": probe.trace_context_meta,
                    "resolved_assets": probe.resolved_assets,
                    "node_payloads": probe.node_payloads,
                    "node_artifacts": probe.node_artifacts,
                }
            )
        scenarios[scenario_name] = {"sequence": sequence, "turns": turns}

    after = _asset_hash_snapshot()

    return {
        "report_version": "silent_collapse_forensics.v1",
        "asset_hash_snapshot_before": before,
        "asset_hash_snapshot_after": after,
        "asset_hashes_mutated": before != after,
        "scenarios": scenarios,
    }


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
