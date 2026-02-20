from __future__ import annotations

from ..schemas import BeliefState, WorldState


def diff_belief_state(prev: BeliefState, new: BeliefState) -> dict:
    diff: dict = {}
    if (prev.get("belief_buckets") or {}) != (new.get("belief_buckets") or {}):
        diff["belief_buckets"] = {
            "before": prev.get("belief_buckets") or {},
            "after": new.get("belief_buckets") or {},
        }
    if (prev.get("planner_signals") or {}) != (new.get("planner_signals") or {}):
        diff["planner_signals"] = {
            "before": prev.get("planner_signals") or {},
            "after": new.get("planner_signals") or {},
        }
    return diff


def top_evidence_v2(world_state: WorldState) -> list[dict]:
    buckets = (world_state.get("world_buckets") or {}) if isinstance(world_state, dict) else {}
    rows: list[dict] = []
    for bucket in ("offers", "constraints", "claims", "requests"):
        values = buckets.get(bucket, []) if isinstance(buckets.get(bucket), list) else []
        for rec in values[:3]:
            if not isinstance(rec, dict):
                continue
            rows.append(
                {
                    "path": f"world_buckets.{bucket}",
                    "value": str(rec.get("text", ""))[:120],
                    "confidence": float(rec.get("confidence", 0.0) or 0.0),
                }
            )
    rows.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)
    return rows[:6]
