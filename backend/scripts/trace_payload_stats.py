import json
import os
from statistics import mean

from state import SessionState
from negotiation.telemetry.live_trace import build_trace_event


def main() -> None:
    session = SessionState(user_id="u", session_id="s")
    sizes = []
    for idx in range(20):
        trace_item = {
            "turn": idx + 1,
            "assistant_reply": "ok",
            "user_message": "hola",
            "world_prev": {"schema_version": "v3", "world_buckets": {"offers": []}, "world_state_meta": {"turn_idx": idx}},
            "world_new": {"schema_version": "v3", "world_buckets": {"offers": [{"text": "9500", "confidence": 0.7}]}, "world_state_meta": {"turn_idx": idx + 1}},
            "world_diff": {"domain": {"world_buckets": {"before": {}, "after": {}}}},
            "belief_prev": {"schema_version": "v3", "belief_buckets": {"hypotheses": []}, "planner_signals": {"interaction_health": "stable", "conflict_risk": 0.0, "recommended_move": "hold", "recovery_mode": False}},
            "belief_new": {"schema_version": "v3", "belief_buckets": {"hypotheses": [{"text": "urgencia", "confidence": 0.6, "status": "active"}]}, "planner_signals": {"interaction_health": "stable", "conflict_risk": 0.0, "recommended_move": "hold", "recovery_mode": False}},
            "belief_diff": {"belief_buckets": {"before": {}, "after": {}}},
            "policy_decision": {"policy_id": "safe_neutral"},
            "phase_effective": {"phase": "interests"},
            "gates": {},
            "planner_meta": {},
            "belief_update_meta": {},
            "progress_debug": {},
            "trace_runtime": {
                "nodes": {
                    "world_updater": {"total_ms": 12, "gates_ms": 2, "normalize_merge_diff_ms": 4, "llm_ms": 7, "entered": True, "skipped": False},
                    "belief_updater": {"total_ms": 6, "gates_ms": 1, "normalize_merge_diff_ms": 3, "llm_ms": 0, "entered": True, "skipped": False},
                    "policy_progress": {"total_ms": 2, "gates_ms": 0, "normalize_merge_diff_ms": 1, "llm_ms": 0, "entered": True, "skipped": False},
                    "phase_policy_planner": {"total_ms": 16, "gates_ms": 2, "normalize_merge_diff_ms": 3, "llm_ms": 12, "entered": True, "skipped": False},
                    "progress_updater": {"total_ms": 4, "gates_ms": 0, "normalize_merge_diff_ms": 2, "llm_ms": 0, "entered": True, "skipped": False},
                    "executor": {"total_ms": 20, "gates_ms": 0, "normalize_merge_diff_ms": 2, "llm_ms": 18, "entered": True, "skipped": False},
                },
                "llm_calls": [
                    {"name": "planner_llm", "node": "phase_policy_planner", "latency_ms": 12, "ok": True},
                    {"name": "executor_llm", "node": "executor", "latency_ms": 18, "ok": True},
                ],
            },
        }
        evt = build_trace_event(user_id="u", session_id="s", session=session, trace_index=idx, trace_item=trace_item)
        sizes.append(len(json.dumps(evt, ensure_ascii=False).encode("utf-8")))
    sizes_sorted = sorted(sizes)
    p95 = sizes_sorted[int(len(sizes_sorted) * 0.95) - 1]
    result = {"events": len(sizes), "avg_bytes": round(mean(sizes), 2), "p95_bytes": p95}
    print(json.dumps(result, ensure_ascii=False))

    budget = int(os.getenv("TRACE_PAYLOAD_P95_BUDGET_BYTES", "0") or 0)
    if budget > 0 and p95 > budget:
        raise SystemExit(f"trace_payload_budget_exceeded p95={p95} budget={budget}")


if __name__ == "__main__":
    main()
