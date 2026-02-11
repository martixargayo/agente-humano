from __future__ import annotations

from pathlib import Path


def _read(rel_path: str) -> str:
    return Path(rel_path).read_text(encoding="utf-8")


def test_guardrail_no_legacy_imports_in_runtime_nodes():
    planner_text = _read("backend/negotiation/nodes/planner_node.py")
    assert "apply_intent_constraints" not in planner_text
    assert "select_policy_id_on_skip" not in planner_text
    assert "gate_phase_policy" not in planner_text

    graph_text = _read("backend/negotiation/negotiation_graph.py")
    assert "intent_manager_node" not in graph_text
