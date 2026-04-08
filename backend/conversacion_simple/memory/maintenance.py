from __future__ import annotations

from typing import Any

from ..state import ConversationSimpleCanonicalState
from .compression import build_compacted_summary
from .fallback import build_deterministic_fallback_summary
from .policy import split_episodic_for_compaction


def schedule_memory_maintenance(*, canonical_state: ConversationSimpleCanonicalState, reason: str, retry_limit: int) -> None:
    canonical_state.memory_maintenance.pending = True
    canonical_state.memory_maintenance.retry_limit = retry_limit
    canonical_state.memory_maintenance.last_reason = reason
    canonical_state.memory_maintenance.last_status = "scheduled"
    canonical_state.memory_maintenance.last_mode = "deferred_v1"


def run_memory_maintenance_best_effort(
    *,
    canonical_state: ConversationSimpleCanonicalState,
    high_resolution_limit: int,
    compacted_summary_max_chars: int,
    simulate_failure: bool = False,
) -> dict[str, Any]:
    obs: dict[str, Any] = {
        "memory_compaction_scheduled": bool(canonical_state.memory_maintenance.pending),
        "memory_compaction_mode": canonical_state.memory_maintenance.last_mode or "none",
        "memory_compaction_status": canonical_state.memory_maintenance.last_status or "idle",
        "memory_compaction_reason": canonical_state.memory_maintenance.last_reason,
        "memory_compacted_summary_chars_before": len(canonical_state.memory_compacted_summary or ""),
        "memory_growth_anomaly_flag": False,
    }
    if not canonical_state.memory_maintenance.pending:
        obs["memory_compacted_summary_chars_after"] = len(canonical_state.memory_compacted_summary or "")
        return obs

    maintenance = canonical_state.memory_maintenance
    maintenance.attempts += 1
    before_count = len(canonical_state.memory_episodic)
    retained, candidates = split_episodic_for_compaction(items=canonical_state.memory_episodic, high_resolution_limit=high_resolution_limit)

    try:
        if simulate_failure:
            raise RuntimeError("simulated_compaction_failure")
        summary = build_compacted_summary(
            previous_summary=canonical_state.memory_compacted_summary,
            candidates=candidates,
            max_chars=compacted_summary_max_chars,
        )
        canonical_state.memory_compacted_summary = summary
        canonical_state.memory_episodic = retained
        maintenance.pending = False
        maintenance.last_status = "completed"
        maintenance.last_mode = "deferred_v1"
        maintenance.last_compacted_turn_id = canonical_state.trace.turn_id
    except Exception:
        if maintenance.attempts >= maintenance.retry_limit:
            canonical_state.memory_compacted_summary = build_deterministic_fallback_summary(
                items=canonical_state.memory_episodic,
                max_chars=compacted_summary_max_chars,
            )
            canonical_state.memory_episodic = retained
            maintenance.pending = False
            maintenance.last_status = "fallback_applied"
            maintenance.last_mode = "deterministic_fallback"
            maintenance.last_compacted_turn_id = canonical_state.trace.turn_id
            obs["memory_compaction_reason"] = "retry_budget_exhausted"
        else:
            maintenance.last_status = "deferred_retry"
            maintenance.last_mode = "deferred_v1"
            obs["memory_compaction_reason"] = "attempt_failed_retry_scheduled"

    after_count = len(canonical_state.memory_episodic)
    obs["memory_episodic_count_before"] = before_count
    obs["memory_episodic_count_after"] = after_count
    obs["memory_compaction_status"] = maintenance.last_status
    obs["memory_compaction_mode"] = maintenance.last_mode
    obs["memory_compaction_scheduled"] = bool(maintenance.pending)
    obs["memory_compacted_summary_chars_after"] = len(canonical_state.memory_compacted_summary or "")
    obs["memory_growth_anomaly_flag"] = after_count > before_count + 8
    if obs.get("memory_compaction_reason") is None:
        obs["memory_compaction_reason"] = maintenance.last_reason
    return obs
