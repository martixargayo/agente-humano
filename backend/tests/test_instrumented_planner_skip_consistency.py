from __future__ import annotations

from negotiation.negotiation_graph import _instrumented_node


def test_instrumented_node_uses_planner_skipped_flag_for_phase_policy_planner():
    wrapped = _instrumented_node(
        "phase_policy_planner",
        lambda state: {
            **state,
            "planner_meta": {"planner_skipped": True},
            "gate_meta": {"planner_skipped": True},
        },
    )

    out = wrapped({"trace_runtime": {"nodes": {}, "llm_calls": []}})

    assert out["planner_meta"]["planner_skipped"] is True
    assert out["gate_meta"]["planner_skipped"] is True
    assert out["trace_runtime"]["nodes"]["phase_policy_planner"]["skipped"] is True

def test_instrumented_node_keeps_planner_skip_triplet_consistent_when_not_skipped():
    wrapped = _instrumented_node(
        "phase_policy_planner",
        lambda state: {
            **state,
            "planner_meta": {"planner_skipped": False},
            "gate_meta": {"planner_skipped": False},
        },
    )

    out = wrapped({"trace_runtime": {"nodes": {}, "llm_calls": []}})

    planner_skipped = out["planner_meta"]["planner_skipped"]
    gate_skipped = out["gate_meta"]["planner_skipped"]
    timing_skipped = out["trace_runtime"]["nodes"]["phase_policy_planner"]["skipped"]
    assert planner_skipped == gate_skipped == timing_skipped

