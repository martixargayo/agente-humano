import json
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
        }
        evt = build_trace_event(user_id="u", session_id="s", session=session, trace_index=idx, trace_item=trace_item)
        sizes.append(len(json.dumps(evt, ensure_ascii=False).encode("utf-8")))
    sizes_sorted = sorted(sizes)
    p95 = sizes_sorted[int(len(sizes_sorted) * 0.95) - 1]
    print(json.dumps({"events": len(sizes), "avg_bytes": round(mean(sizes), 2), "p95_bytes": p95}, ensure_ascii=False))


if __name__ == "__main__":
    main()
