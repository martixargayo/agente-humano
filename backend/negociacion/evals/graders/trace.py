from __future__ import annotations

from typing import Any


def get_latest_rich_trace(world_state: dict[str, Any], memory_key: str) -> dict[str, Any] | None:
    traces = world_state.get(f"{memory_key}_traces", [])
    if not isinstance(traces, list) or not traces:
        return None
    latest = traces[-1]
    return latest if isinstance(latest, dict) else None


def has_required_node_blocks(rich_trace: dict[str, Any], node_names: list[str] | None = None) -> bool:
    required = node_names or ["memory", "phase_classifier", "planner", "executor"]
    nodes = rich_trace.get("nodes", {})
    if not isinstance(nodes, dict):
        return False
    return all(node in nodes for node in required)
