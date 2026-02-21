from __future__ import annotations

import hashlib
import json
import time

from ..extractors.belief_extractor_v1 import extract_belief_state_llm_v1
from ..schemas import default_belief_state, default_progress_state
from ..state.deps import DEFAULT_DEPS
from ..telemetry.trace_runtime import record_llm_call


def _state_fingerprint(value: dict) -> str:
    payload = json.dumps(value or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _world_changed_meaningfully(*, world_diff: dict, prev_world: dict, world: dict) -> bool:
    domain = world_diff.get("domain") if isinstance(world_diff, dict) else None
    if isinstance(domain, dict):
        world_buckets_delta = domain.get("world_buckets")
        if world_buckets_delta not in (None, {}, []):
            return True
    if isinstance(world_diff, dict):
        world_buckets_delta = world_diff.get("world_buckets")
        if world_buckets_delta not in (None, {}, []):
            return True
    prev_buckets = (prev_world.get("world_buckets") or {}) if isinstance(prev_world, dict) else {}
    new_buckets = (world.get("world_buckets") or {}) if isinstance(world, dict) else {}
    return prev_buckets != new_buckets


def belief_updater_node(state: dict) -> dict:
    deps = state.get("deps", DEFAULT_DEPS)
    prev_belief = state.get("belief_state") or default_belief_state()
    state["prev_belief_state"] = prev_belief
    gate_state = (state.get("progress_state") or {}).get(
        "gate_state", default_progress_state()["gate_state"]
    )
    world_changed = _world_changed_meaningfully(
        world_diff=state.get("world_diff", {}),
        prev_world=state.get("prev_world_state", {}),
        world=state.get("world_state", {}),
    )

    prev_belief_fp = _state_fingerprint(prev_belief)
    if not world_changed:
        belief_state = prev_belief
        belief_meta = {
            "belief_update_failed": False,
            "belief_update_error": "",
            "belief_update_skipped": True,
            "skip_reason": "no_world_delta",
            "belief_node_entered": True,
            "belief_updater_invoked": False,
            "belief_noop_reason": "gate_skipped",
            "belief_engine": "llm_belief_extractor_v1",
            "belief_llm_used": False,
        }
    else:
        llm_started = time.perf_counter()
        try:
            belief_state, llm_meta = extract_belief_state_llm_v1(
                deps=deps,
                user_message=state.get("user_message", ""),
                world_state=state.get("world_state", {}),
                prev_belief_state=prev_belief,
                turn_idx=int(state.get("turn_count", 0) or 0),
            )
            record_llm_call(
                state,
                name="belief_llm",
                node="belief_updater",
                started=llm_started,
                ok=True,
                error_stage="",
                error="",
                input_prompt_rendered=str(llm_meta.get("belief_input_prompt_rendered", "")),
                output_text_rendered=str(llm_meta.get("belief_output_text_rendered", "")),
                input_payload_raw=llm_meta.get("belief_input_payload_raw"),
                output_payload_raw=llm_meta.get("belief_output_payload_raw"),
            )
            belief_meta = {
                "belief_update_failed": False,
                "belief_update_error": "",
                "belief_update_skipped": False,
                "skip_reason": "",
                "belief_node_entered": True,
                "belief_updater_invoked": True,
                "belief_noop_reason": "",
                "belief_engine": "llm_belief_extractor_v1",
                "belief_llm_used": True,
                "belief_latency_ms": int(llm_meta.get("belief_latency_ms", 0) or 0),
            }
        except Exception as exc:
            record_llm_call(
                state,
                name="belief_llm",
                node="belief_updater",
                started=llm_started,
                ok=False,
                error_stage="belief_extract",
                error=str(exc),
            )
            belief_state = prev_belief
            belief_meta = {
                "belief_update_failed": True,
                "belief_update_error": str(exc),
                "belief_update_skipped": True,
                "skip_reason": "belief_llm_error",
                "belief_node_entered": True,
                "belief_updater_invoked": True,
                "belief_noop_reason": "llm_error_reuse_prev",
                "belief_engine": "llm_belief_extractor_v1",
                "belief_llm_used": True,
            }

    curr_belief_fp = _state_fingerprint(belief_state)
    belief_meta["belief_gate_decision"] = {
        "skipped": bool(belief_meta.get("belief_update_skipped", False)),
        "reason": str(belief_meta.get("skip_reason", "")),
        "world_changed_meaningfully": bool(world_changed),
        "prev_belief_fp": prev_belief_fp or None,
        "curr_belief_fp": curr_belief_fp or None,
    }

    prev_buckets = (prev_belief.get("belief_buckets") or {}) if isinstance(prev_belief, dict) else {}
    curr_buckets = (belief_state.get("belief_buckets") or {}) if isinstance(belief_state, dict) else {}
    bucket_names = sorted(set(prev_buckets.keys()) | set(curr_buckets.keys()))
    changed: list[str] = []
    counts_delta: dict[str, dict] = {}
    for bucket in bucket_names:
        b = prev_buckets.get(bucket, [])
        a = curr_buckets.get(bucket, [])
        b_count = len(b) if isinstance(b, list) else 0
        a_count = len(a) if isinstance(a, list) else 0
        if b != a:
            changed.append(bucket)
            counts_delta[bucket] = {"before": b_count, "after": a_count, "delta": a_count - b_count}
    planner_signals = ((belief_state or {}).get("planner_signals") or {}) if isinstance(belief_state, dict) else {}
    state["belief_debug"] = {
        "belief_diff_bucket_summary": {
            "changed_buckets": changed[:12],
            "counts_delta": counts_delta,
        },
        "belief_update_meta": {
            "belief_update_skipped": bool(belief_meta.get("belief_update_skipped", False)),
            "belief_llm_failed": bool(belief_meta.get("belief_update_failed", False)),
            "belief_fallback_used": bool(belief_meta.get("belief_noop_reason", "") == "llm_error_reuse_prev"),
            "belief_latency_ms": int(belief_meta.get("belief_latency_ms", 0) or 0),
        },
        "planner_relevant": {
            "interaction_health": str(planner_signals.get("interaction_health", "stable")),
            "conflict_risk": float(planner_signals.get("conflict_risk", 0.0) or 0.0),
            "recovery_mode": bool(planner_signals.get("recovery_mode", False)),
            "recommended_move": str(planner_signals.get("recommended_move", "hold")),
        },
    }
    state["belief_state"] = belief_state
    state["belief_update_meta"] = belief_meta
    state["progress_state"]["gate_state"] = gate_state
    return state
