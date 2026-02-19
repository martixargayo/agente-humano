from __future__ import annotations

from datetime import datetime
import os
from typing import Any

from state import SessionState


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
    for gate_key in sorted(gates.keys()):
        value = gates.get(gate_key)
        if isinstance(value, bool):
            selected = "enabled" if value else "skipped"
            if gate_key.endswith("_skipped"):
                selected = "skipped" if value else "enabled"
            choices.append(
                {
                    "gate": gate_key,
                    "selected": selected,
                    "value": value,
                }
            )
    return choices


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

    return {
        "user_id": user_id,
        "session_id": session_id,
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
        "world_diff_keys": sorted((trace_item.get("world_diff") or {}).keys()),
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
            key for key, value in gate_meta.items() if isinstance(value, bool) and value
        ),
        "gate_choices": _gate_choices(gate_meta),
        "gates": gate_meta,
        "extractor_used": bool(trace_item.get("extractor_used", False)),
        "extractor_reasons": trace_item.get("extractor_reasons") or [],
        "extractor_world_patch_keys": trace_item.get("extractor_world_patch_keys") or [],
        "raw_llm_patch_keys": trace_item.get("raw_llm_patch_keys") or {},
        "filtered_patch_keys": trace_item.get("filtered_patch_keys") or {},
        "dropped_patch_keys": trace_item.get("dropped_patch_keys") or {},
        "open_claims_raw_count": int(trace_item.get("open_claims_raw_count") or 0),
        "open_claims_kept_count": int(trace_item.get("open_claims_kept_count") or 0),
        "rejected_claims": trace_item.get("rejected_claims") or [],
        "merged_changed_paths": trace_item.get("merged_changed_paths") or [],
        "diff_paths": trace_item.get("diff_paths") or [],
        "backstop_reasons": trace_item.get("backstop_reasons") or [],
        "fallback_applied": bool(trace_item.get("fallback_applied", False)),
        "fallback_reasons": trace_item.get("fallback_reasons") or [],
        "unknown_claims_added_count": int(trace_item.get("unknown_claims_added_count") or 0),
        "extractor_confidence_summary": trace_item.get("extractor_confidence_summary") or {},
        "top_evidence_v2": trace_item.get("top_evidence_v2") or [],
        "unknown_claims_count": int(trace_item.get("unknown_claims_count") or 0),
        "validation_issues": trace_item.get("validation_issues") or {},
        "exit_issues": exit_issues,
        "timing": {
            "t_turn_start": trace_item.get("t_turn_start", 0.0),
            "t_before_graph": trace_item.get("t_before_graph", 0.0),
            "t_after_graph": trace_item.get("t_after_graph", 0.0),
            "t_reply_saved": trace_item.get("t_reply_saved", 0.0),
            "t_summary_enqueued": trace_item.get("t_summary_enqueued", 0.0),
        },
        "planner_reason": planner_meta.get("reason", ""),
        "phase_candidate": trace_item.get("phase_candidate") or {},
        "phase_effective": trace_item.get("phase_effective") or {},
        "policy_decision": trace_item.get("policy_decision") or {},
        "policy_pre_repair": trace_item.get("policy_pre_repair") or {},
        "policy_post_repair": trace_item.get("policy_post_repair") or {},
        "executed_policy": trace_item.get("executed_policy_normalized") or {},
        "intent": {
            "step_kind": trace_item.get("intent_step_kind", ""),
            "target_slot": trace_item.get("intent_target_slot", ""),
            "decision": trace_item.get("intent_decision", ""),
            "transition": trace_item.get("intent_transition", ""),
            "pivot_reason": trace_item.get("intent_pivot_reason", ""),
            "pivot_strategy": trace_item.get("intent_pivot_strategy", ""),
            "commitment_level": trace_item.get("intent_commitment_level", ""),
            "slots_delta": trace_item.get("intent_slots_delta") or {},
            "success_reasons": trace_item.get("intent_success_reasons") or [],
        },
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
        "raw": trace_item,
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
