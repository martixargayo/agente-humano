from __future__ import annotations

from typing import Any

from state import SESSIONS, SessionState


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _build_gate_nodes(trace_item: dict[str, Any], seq_start: int = 0) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    seq = seq_start

    planner_debug = _safe_dict(trace_item.get("planner_debug"))
    gate_decision = _safe_dict(planner_debug.get("gate_decision"))
    if gate_decision:
        nodes.append(
            {
                "node_id": f"gate-{seq}",
                "node_name": "planner_gate",
                "node_type": "gate",
                "sequence_index": seq,
                "latency_ms": int(gate_decision.get("latency_ms", 0) or 0),
                "status": "ok",
                "input_payload_raw": {
                    "gate_path": gate_decision.get("gate_path"),
                    "reason_codes": gate_decision.get("gate_reason_codes", []),
                    "judgement": trace_item.get("policy_plan_judgement", {}),
                },
                "output_payload_raw": {
                    "decision": gate_decision.get("gate_path", "unknown"),
                },
                "gate_evidence": {
                    "allowed_policy_ids": trace_item.get("allowed_policy_ids", []),
                    "phase_effective": trace_item.get("phase_effective", {}),
                },
                "gate_decision": gate_decision.get("gate_path", "unknown"),
                "gate_decision_reason": ", ".join(gate_decision.get("gate_reason_codes", [])),
            }
        )
        seq += 1

    belief_meta = _safe_dict(trace_item.get("belief_update_meta"))
    belief_gate = _safe_dict(belief_meta.get("belief_gate_decision"))
    if belief_gate:
        nodes.append(
            {
                "node_id": f"gate-{seq}",
                "node_name": "belief_update_gate",
                "node_type": "gate",
                "sequence_index": seq,
                "latency_ms": 0,
                "status": "ok",
                "input_payload_raw": {
                    "world_changed_meaningfully": belief_gate.get("world_changed_meaningfully"),
                    "prev_belief_fp": belief_gate.get("prev_belief_fp"),
                },
                "output_payload_raw": {
                    "skipped": belief_gate.get("skipped"),
                },
                "gate_evidence": {
                    "world_diff": trace_item.get("world_diff", {}),
                },
                "gate_decision": "skipped" if belief_gate.get("skipped") else "executed",
                "gate_decision_reason": str(belief_gate.get("reason", "")),
            }
        )
    return nodes


def build_livetrace2_event(*, user_id: str, session_id: str, session: SessionState, trace_index: int, trace_item: dict[str, Any]) -> dict[str, Any]:
    runtime = _safe_dict(trace_item.get("trace_runtime"))
    llm_calls = list(runtime.get("llm_calls", [])) if isinstance(runtime.get("llm_calls"), list) else []

    nodes: list[dict[str, Any]] = []
    for idx, llm in enumerate(llm_calls):
        if not isinstance(llm, dict):
            continue
        nodes.append(
            {
                "node_id": f"llm-{idx}",
                "node_name": llm.get("name", "llm"),
                "node_type": "llm_call",
                "sequence_index": idx,
                "started_at": llm.get("start_ts", ""),
                "ended_at": llm.get("end_ts", ""),
                "latency_ms": int(llm.get("latency_ms", 0) or 0),
                "status": "ok" if bool(llm.get("ok", False)) else "error",
                "error": llm.get("error", ""),
                "input_payload_raw": llm.get("input_payload_raw"),
                "input_prompt_rendered": llm.get("input_prompt_rendered", ""),
                "output_payload_raw": llm.get("output_payload_raw"),
                "output_text_rendered": llm.get("output_text_rendered", ""),
                "model": llm.get("model"),
                "tokens_in": llm.get("tokens_in"),
                "tokens_out": llm.get("tokens_out"),
                "source_node": llm.get("node"),
            }
        )

    gate_nodes = _build_gate_nodes(trace_item, seq_start=len(nodes))
    nodes.extend(gate_nodes)
    nodes = sorted(nodes, key=lambda item: int(item.get("sequence_index", 0)))

    for i, node in enumerate(nodes):
        node["prev_node_id"] = nodes[i - 1]["node_id"] if i > 0 else None
        node["next_node_ids"] = [nodes[i + 1]["node_id"]] if i + 1 < len(nodes) else []

    total_latency = sum(int(node.get("latency_ms", 0) or 0) for node in nodes)

    return {
        "trace_schema_version": "livetrace2-mvp-1",
        "user_id": user_id,
        "session_id": session_id,
        "trace_index": trace_index,
        "turn": trace_item.get("turn", 0),
        "updated_at": session.last_updated.isoformat(),
        "input_message": trace_item.get("user_message", ""),
        "final_reply": trace_item.get("assistant_reply", ""),
        "turn_total_latency_ms": total_latency,
        "nodes": nodes,
    }


def list_recent_livetrace2_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for (user_id, session_id), session in sorted(SESSIONS.items(), key=lambda item: item[1].last_updated):
        trace = session.debug_trace or []
        for trace_index, trace_item in enumerate(trace[-30:]):
            if not isinstance(trace_item, dict):
                continue
            events.append(
                build_livetrace2_event(
                    user_id=user_id,
                    session_id=session_id,
                    session=session,
                    trace_index=trace_index,
                    trace_item=trace_item,
                )
            )
    return events
