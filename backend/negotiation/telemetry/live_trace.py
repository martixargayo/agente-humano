from __future__ import annotations

from datetime import datetime
import os
from typing import Any

from state import SessionState
from .trace_runtime import init_trace_runtime, trace_include_internals, trace_level
from ..world_diff_debug import world_diff_keys_for_debug


def _json_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return sorted(value.keys())
    return []


def _changed_unchanged(prev: Any, new: Any) -> tuple[list[str], list[str]]:
    if not isinstance(prev, dict) or not isinstance(new, dict):
        return [], []
    shared = set(prev.keys()) & set(new.keys())
    changed = sorted(key for key in shared if prev.get(key) != new.get(key))
    unchanged = sorted(key for key in shared if prev.get(key) == new.get(key))
    return changed, unchanged


def _gate_choices(gates: dict[str, Any]) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    skip_reasons = gates.get("skip_reasons") if isinstance(gates.get("skip_reasons"), dict) else {}
    for gate_key in sorted(gates.keys()):
        value = gates.get(gate_key)
        if not isinstance(value, bool):
            continue
        gate_enabled = True
        gate_decision = "skipped" if value else "executed"
        gate_reason = ""
        logical_gate = gate_key
        if gate_key.endswith("_skipped"):
            logical_gate = gate_key.removesuffix("_skipped")
            gate_reason = str(skip_reasons.get(logical_gate, "") or "")
        choices.append(
            {
                "gate": logical_gate,
                "gate_enabled": gate_enabled,
                "gate_decision": gate_decision,
                "gate_reason": gate_reason,
                "raw_flag": gate_key,
                "raw_value": value,
            }
        )
    return choices




def _duration_ms(start: Any, end: Any) -> int:
    try:
        return max(0, int((float(end) - float(start)) * 1000))
    except Exception:
        return 0


def _safe_text(value: Any, max_chars: int = 240) -> str:
    return str(value or "")[:max(1, max_chars)]


def _timing_payload(trace_item: dict[str, Any]) -> dict[str, Any]:
    timing_prev = trace_item.get("timing") if isinstance(trace_item.get("timing"), dict) else {}
    runtime = trace_item.get("trace_runtime") if isinstance(trace_item.get("trace_runtime"), dict) else init_trace_runtime()
    timeline = {
        "t_turn_start": trace_item.get("t_turn_start", 0.0),
        "t_before_graph": trace_item.get("t_before_graph", 0.0),
        "t_after_graph": trace_item.get("t_after_graph", 0.0),
        "t_reply_saved": trace_item.get("t_reply_saved", 0.0),
        "t_summary_enqueued": trace_item.get("t_summary_enqueued", 0.0),
    }
    llm_calls = list(runtime.get("llm_calls", [])[:12])
    planner_meta = trace_item.get("planner_meta") or {}
    planner_debug_llm = ((trace_item.get("planner_debug") or {}).get("llm_call") or {})
    planner_llm_called = bool(planner_meta.get("planner_llm_called", False) or planner_debug_llm.get("planner_llm_called", False))
    has_planner_call = any(str(item.get("node", "")) == "phase_policy_planner" for item in llm_calls if isinstance(item, dict))
    if planner_llm_called and not has_planner_call:
        planner_latency = int(planner_meta.get("planner_latency_ms", planner_debug_llm.get("planner_latency_ms", 0)) or 0)
        llm_calls.append(
            {
                "name": "planner_llm",
                "node": "phase_policy_planner",
                "start_ts": "",
                "end_ts": "",
                "latency_ms": max(1, planner_latency),
                "model": None,
                "tokens_in": None,
                "tokens_out": None,
                "retry_count": 1 if bool(planner_meta.get("planner_fallback_used", False)) else 0,
                "ok": not bool(planner_meta.get("planner_failed", False)),
                "error_stage": str(planner_meta.get("planner_error_stage", "")),
                "error": _safe_text(planner_meta.get("planner_error", ""), 240),
            }
        )
    payload = {
        **timing_prev,
        "turn_total_ms": _duration_ms(timeline["t_turn_start"], timeline["t_summary_enqueued"]),
        "timeline": timeline,
        "nodes": runtime.get("nodes", {}),
        "llm_calls": llm_calls[:12],
    }
    trace_perf = trace_item.get("trace_perf") if isinstance(trace_item.get("trace_perf"), dict) else {}
    if trace_perf:
        payload["trace_perf"] = trace_perf
    return payload


def _internal_payload(trace_item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not trace_include_internals():
        return {}, {}
    planner_v2 = trace_item.get("planner_debug_v2") or {}
    if not planner_v2:
        planner = trace_item.get("planner_debug") or {}
        planner_v2 = {
            "input_compact": {
                "planner_request": (planner.get("inputs") or {}).get("planner_request"),
                "allowed_policy_ids": trace_item.get("allowed_policy_ids") or [],
                "gate_decisions_influential": planner.get("gate_decision") or {},
                "phase_effective": trace_item.get("phase_effective") or {},
            },
            "output": {
                "selected_policy": (trace_item.get("policy_decision") or {}).get("policy_id", ""),
                "policy_ranking_top5": list((trace_item.get("phase_candidate") or {}).get("alternatives", []))[:5],
                "normalization": {
                    "changed": bool((trace_item.get("planner_meta") or {}).get("policy_normalization_changed", False)),
                    "issues": list((trace_item.get("planner_meta") or {}).get("issues", []))[:8],
                },
                "fallback": {
                    "used": bool((trace_item.get("planner_meta") or {}).get("planner_fallback_used", False)),
                    "reason": _safe_text((trace_item.get("planner_meta") or {}).get("planner_error", ""), 140),
                },
            },
            "reasoning_trace": {
                "selected_policy": (trace_item.get("policy_decision") or {}).get("policy_id", ""),
                "why_short": _safe_text((trace_item.get("policy_decision") or {}).get("why_short", ""), 140),
                "key_factors": list((trace_item.get("phase_candidate") or {}).get("reasons", []))[:6],
                "rejected_alternatives": list((trace_item.get("phase_candidate") or {}).get("alternatives", []))[:4],
            },
        }
    executor_v2 = trace_item.get("executor_debug_v2") or {}
    if not executor_v2:
        val_meta = trace_item.get("executor_validator_meta") or {}
        executor_v2 = {
            "output_meta": {
                "response_length": len(str(trace_item.get("assistant_reply", "") or "")),
                "constraints_respected": not bool(val_meta.get("fallback_applied", False)),
                "sanitizer_flags": list(val_meta.get("validation_flags", []))[:8],
            }
        }
    return planner_v2, executor_v2

def build_trace_event(
    *,
    user_id: str,
    session_id: str,
    session: SessionState,
    trace_index: int,
    trace_item: dict[str, Any],
) -> dict[str, Any]:
    planner_meta = trace_item.get("planner_meta") or {}
    gate_meta = trace_item.get("gates") or {}
    world_prev = trace_item.get("world_prev") or {}
    world_new = trace_item.get("world_new") or {}
    belief_prev = trace_item.get("belief_prev") or {}
    belief_new = trace_item.get("belief_new") or {}
    world_changed, world_unchanged = _changed_unchanged(world_prev, world_new)
    belief_changed_keys, belief_unchanged = _changed_unchanged(belief_prev, belief_new)

    build_git_sha_source = "unknown"
    build_git_sha = trace_item.get("build_git_sha")
    if build_git_sha:
        build_git_sha_source = "trace_item"
    elif os.getenv("BUILD_GIT_SHA"):
        build_git_sha = os.getenv("BUILD_GIT_SHA")
        build_git_sha_source = "env_BUILD_GIT_SHA"
    elif os.getenv("GIT_SHA"):
        build_git_sha = os.getenv("GIT_SHA")
        build_git_sha_source = "env_GIT_SHA"
    elif os.getenv("BUILD_ID"):
        build_git_sha = os.getenv("BUILD_ID")
        build_git_sha_source = "env_BUILD_ID"
    else:
        build_git_sha = "unknown"

    exit_issues = list(trace_item.get("exit_issues") or [])
    if str(build_git_sha) == "unknown" and "build_sha_unknown" not in exit_issues:
        exit_issues.append("build_sha_unknown")

    belief_meta = trace_item.get("belief_update_meta") or {}
    belief_diff_keys = sorted((trace_item.get("belief_diff") or {}).keys())
    belief_updated_fields = [str(key) for key in (belief_meta.get("belief_updated_fields") or []) if key]
    belief_changed = bool(
        belief_diff_keys
        or belief_changed_keys
        or belief_meta.get("belief_merge_changed", False)
    )
    if not belief_diff_keys and belief_changed and belief_updated_fields:
        belief_diff_keys = sorted(set(belief_updated_fields))
    if belief_changed and "belief_buckets" in belief_updated_fields and "belief_buckets" not in belief_changed_keys:
        belief_changed_keys.append("belief_buckets")

    planner_internal, executor_internal = _internal_payload(trace_item)

    return {
        "user_id": user_id,
        "session_id": session_id,
        "trace_schema_version": "vNext-1" if trace_level() >= 1 else "v1",
        "trace_index": trace_index,
        "turn": trace_item.get("turn", 0),
        "updated_at": session.last_updated.isoformat(),
        "final_reply": trace_item.get("assistant_reply", ""),
        "input_message": trace_item.get("user_message", ""),
        "planner_failed": bool(trace_item.get("planner_failed", False)),
        "belief_update_failed": bool(trace_item.get("belief_update_failed", False)),
        "planner_error": trace_item.get("planner_error", ""),
        "belief_update_error": trace_item.get("belief_update_error", ""),
        "planner_fallback_used": bool(trace_item.get("planner_fallback_used", False)),
        "policy": (trace_item.get("policy_decision") or {}).get("policy_id", ""),
        "phase": (trace_item.get("phase_effective") or {}).get("phase", ""),
        "allowed_policy_ids": trace_item.get("allowed_policy_ids") or [],
        "world_diff_keys": world_diff_keys_for_debug(
            world_diff=trace_item.get("world_diff"),
            world_state=trace_item.get("world_new") or trace_item.get("world_state") or {},
        ),
        "belief_diff_keys": belief_diff_keys,
        "world_base_keys": _json_keys(world_prev),
        "world_new_keys": _json_keys(world_new),
        "world_changed_keys": world_changed,
        "world_unchanged_keys": world_unchanged,
        "belief_base_keys": _json_keys(belief_prev),
        "belief_new_keys": _json_keys(belief_new),
        "belief_changed_keys": belief_changed_keys,
        "belief_unchanged_keys": belief_unchanged,
        "build_git_sha": str(build_git_sha),
        "build_git_sha_source": build_git_sha_source,
        "belief_node_entered": bool(belief_meta.get("belief_node_entered", False)),
        "belief_updater_invoked": bool(belief_meta.get("belief_updater_invoked", False)),
        "belief_noop_reason": str(belief_meta.get("belief_noop_reason", "")),
        "belief_changed": belief_changed,
        "gates_triggered": sorted(
            key.removesuffix("_skipped")
            for key, value in gate_meta.items()
            if isinstance(value, bool) and value
        ),
        "gate_choices": _gate_choices(gate_meta),
        "gates": gate_meta,
        "extractor_used": bool(trace_item.get("extractor_used", False)),
        "extractor_reasons": trace_item.get("extractor_reasons") or [],
        "extractor_world_patch_keys": trace_item.get("extractor_world_patch_keys") or [],
        "merged_changed_paths": trace_item.get("merged_changed_paths") or [],
        "diff_paths": trace_item.get("diff_paths") or [],
        "backstop_reasons": trace_item.get("backstop_reasons") or [],
        "fallback_applied": bool(trace_item.get("fallback_applied", False)),
        "fallback_reasons": trace_item.get("fallback_reasons") or [],
        "extractor_confidence_summary": trace_item.get("extractor_confidence_summary") or {},
        "top_evidence_v2": trace_item.get("top_evidence_v2") or [],
        "validation_issues": trace_item.get("validation_issues") or {},
        "exit_issues": exit_issues,
        "timing": _timing_payload(trace_item),
        "planner_reason": planner_meta.get("reason", ""),
        "phase_candidate": trace_item.get("phase_candidate") or {},
        "phase_effective": trace_item.get("phase_effective") or {},
        "policy_decision": trace_item.get("policy_decision") or {},
        "policy_plan_judgement": trace_item.get("policy_plan_judgement") or {},
        "policy_pre_repair": trace_item.get("policy_pre_repair") or {},
        "policy_post_repair": trace_item.get("policy_post_repair") or {},
        "executed_policy": trace_item.get("executed_policy_normalized") or {},
        "planner_meta": planner_meta,
        "advisor_meta": trace_item.get("advisor_meta") or {},
        "advisor_recs": trace_item.get("advisor_recs") or {},
        "advisor_top_moves": list(((trace_item.get("advisor_recs") or {}).get("recommended_moves") or []))[:3],
        "world_base": world_prev,
        "world_new": world_new,
        "world_diff": trace_item.get("world_diff") or {},
        "belief_base": belief_prev,
        "belief_new": belief_new,
        "belief_diff": trace_item.get("belief_diff") or {},
        "planner_debug": trace_item.get("planner_debug") or {},
        "progress_debug": trace_item.get("progress_debug") or {},
        "world_timers": ((trace_item.get("world_debug") or {}).get("timers") or {}),
        "planner_debug_v2": planner_internal,
        "executor_debug_v2": executor_internal,
        "memory_meta": trace_item.get("memory_meta") or {},
        "refresh_meta": trace_item.get("refresh_meta") or {},
        "summary_enqueue_meta": trace_item.get("summary_enqueue_meta") or {},
        "debug": {
            "belief": belief_meta,
        },
        "model_params": {
            key: value
            for key, value in trace_item.items()
            if key.startswith("negotiation_") or key.endswith("_model") or key.endswith("_temperature")
        },
    }


def list_recent_trace_events(
    sessions: dict[tuple[str, str], SessionState],
    *,
    max_sessions: int = 8,
    max_traces_per_session: int = 20,
) -> list[dict[str, Any]]:
    ordered_sessions = sorted(
        sessions.items(),
        key=lambda item: item[1].last_updated,
        reverse=True,
    )[: max(1, max_sessions)]

    events: list[dict[str, Any]] = []
    for (user_id, session_id), session in ordered_sessions:
        trace = session.debug_trace or []
        start = max(0, len(trace) - max(1, max_traces_per_session))
        for idx in range(start, len(trace)):
            events.append(
                build_trace_event(
                    user_id=user_id,
                    session_id=session_id,
                    session=session,
                    trace_index=idx,
                    trace_item=trace[idx],
                )
            )
    events.sort(
        key=lambda event: (
            datetime.fromisoformat(event["updated_at"]),
            int(event.get("turn") or 0),
            int(event.get("trace_index") or 0),
        )
    )
    return events
