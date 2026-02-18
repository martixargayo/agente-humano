from __future__ import annotations

from datetime import datetime
from typing import Any

from state import SessionState


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
    return {
        "user_id": user_id,
        "session_id": session_id,
        "trace_index": trace_index,
        "turn": trace_item.get("turn", 0),
        "updated_at": session.last_updated.isoformat(),
        "planner_failed": bool(trace_item.get("planner_failed", False)),
        "belief_update_failed": bool(trace_item.get("belief_update_failed", False)),
        "policy": (trace_item.get("policy_decision") or {}).get("policy_id", ""),
        "phase": (trace_item.get("phase_effective") or {}).get("phase", ""),
        "world_diff_keys": sorted((trace_item.get("world_diff") or {}).keys()),
        "belief_diff_keys": sorted((trace_item.get("belief_diff") or {}).keys()),
        "gates_triggered": sorted(
            key
            for key, value in gate_meta.items()
            if isinstance(value, bool) and value
        ),
        "extractor_used": bool(trace_item.get("extractor_used", False)),
        "planner_reason": planner_meta.get("reason", ""),
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
