from __future__ import annotations

from datetime import datetime
import os
from typing import Any

from state import SESSIONS, SessionState


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _safe_json(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return str(value)


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {"_redacted": True, "keys": sorted(value.keys())[:32]}
    if isinstance(value, list):
        return {"_redacted": True, "items": len(value)}
    if value is None:
        return None
    return "[REDACTED]"


def _apply_redaction(node: dict[str, Any]) -> dict[str, Any]:
    mode = os.getenv("LIVETRACE2_MODE", "public").strip().lower()
    fields_raw = os.getenv(
        "LIVETRACE2_REDACT_FIELDS",
        "user_message,memory_block,recent_history,memory_short,memory_long,world_json,belief_state_summary",
    )
    redact_fields = {item.strip() for item in fields_raw.split(",") if item.strip()}

    node_out = dict(node)
    node_out["redaction_applied"] = False
    node_out["redaction_policy_id"] = "none"
    node_out["fields_redacted"] = []

    if mode == "internal":
        return node_out

    prompt = str(node_out.get("input_prompt_rendered") or "")
    output_text = str(node_out.get("output_text_rendered") or "")
    redacted = False
    for key in redact_fields:
        marker = str(key)
        if marker and marker in prompt:
            redacted = True
            prompt = prompt.replace(marker, f"{marker}[REDACTED]")
        if marker and marker in output_text:
            redacted = True
            output_text = output_text.replace(marker, f"{marker}[REDACTED]")

    if redacted:
        node_out["input_prompt_rendered"] = prompt
        node_out["output_text_rendered"] = output_text

    if node_out.get("input_payload_raw") is not None:
        node_out["input_payload_raw"] = _redact_payload(node_out.get("input_payload_raw"))
        node_out["fields_redacted"].append("input_payload_raw")
        redacted = True
    if node_out.get("output_payload_raw") is not None:
        node_out["output_payload_raw"] = _redact_payload(node_out.get("output_payload_raw"))
        node_out["fields_redacted"].append("output_payload_raw")
        redacted = True

    if redacted:
        node_out["redaction_applied"] = True
        node_out["redaction_policy_id"] = "livetrace2-public-v1"
    return node_out


def _build_llm_nodes(trace_id: str, session_id: str, turn_idx: int, runtime: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    llm_calls = list(runtime.get("llm_calls", [])) if isinstance(runtime.get("llm_calls"), list) else []
    for idx, llm in enumerate(llm_calls):
        if not isinstance(llm, dict):
            continue
        status = str(llm.get("status", "") or ("ok" if bool(llm.get("ok", False)) else "error"))
        out.append(
            {
                "trace_id": trace_id,
                "session_id": session_id,
                "turn_idx": turn_idx,
                "node_id": f"llm-{idx}",
                "node_name": str(llm.get("name", "llm")),
                "node_type": "llm_call",
                "status": status,
                "started_at": str(llm.get("start_ts", "") or ""),
                "ended_at": str(llm.get("end_ts", "") or ""),
                "latency_ms": int(llm.get("latency_ms", 0) or 0),
                "sequence_index": 0,
                "input_prompt_rendered": str(llm.get("input_prompt_rendered", "") or ""),
                "input_payload_raw": _safe_json(llm.get("input_payload_raw")),
                "output_text_rendered": str(llm.get("output_text_rendered", "") or ""),
                "output_text_raw": str(llm.get("output_text_rendered", "") or "") or None,
                "output_payload_raw": _safe_json(llm.get("output_payload_raw")),
                "output_payload_parsed": _safe_json(llm.get("output_payload_raw")),
                "model": llm.get("model"),
                "tokens_in": llm.get("tokens_in"),
                "tokens_out": llm.get("tokens_out"),
                "retry_count": int(llm.get("retry_count", 0) or 0),
                "ok": bool(llm.get("ok", False)),
                "error_stage": str(llm.get("error_stage", "") or ""),
                "error": str(llm.get("error", "") or ""),
                "queue_ms": llm.get("queue_ms"),
                "ttfb_ms": llm.get("ttfb_ms"),
                "gate_rule_id": "",
                "gate_version": "",
                "gate_inputs": None,
                "gate_decision": "",
                "gate_reason": "",
                "gate_reason_codes": [],
                "input_capture_state": "captured" if str(llm.get("input_prompt_rendered", "") or "") or llm.get("input_payload_raw") is not None else "not_captured",
                "output_capture_state": "captured" if str(llm.get("output_text_rendered", "") or "") or llm.get("output_payload_raw") is not None else "not_captured",
                "input_truncation": llm.get("input_prompt_meta"),
                "output_truncation": llm.get("output_text_meta"),
            }
        )
    return out


def _build_gate_nodes(trace_id: str, session_id: str, turn_idx: int, runtime: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    gate_events = list(runtime.get("gate_events", [])) if isinstance(runtime.get("gate_events"), list) else []
    for idx, gate in enumerate(gate_events):
        if not isinstance(gate, dict):
            continue
        out.append(
            {
                "trace_id": trace_id,
                "session_id": session_id,
                "turn_idx": turn_idx,
                "node_id": f"gate-{idx}",
                "node_name": str(gate.get("name", "gate")),
                "node_type": "gate",
                "status": str(gate.get("status", "ok") or "ok"),
                "started_at": str(gate.get("start_ts", "") or ""),
                "ended_at": str(gate.get("end_ts", "") or ""),
                "latency_ms": int(gate.get("latency_ms", 0) or 0),
                "sequence_index": 0,
                "input_prompt_rendered": "",
                "input_payload_raw": _safe_json(gate.get("gate_inputs")),
                "output_text_rendered": "",
                "output_text_raw": None,
                "output_payload_raw": {
                    "gate_decision": str(gate.get("decision", "executed") or "executed"),
                    "gate_decision_reason": str(gate.get("reason", "") or ""),
                    "reason_codes": list(gate.get("reason_codes", [])) if isinstance(gate.get("reason_codes"), list) else [],
                    "skipped": str(gate.get("decision", "executed") or "executed") == "skipped",
                },
                "output_payload_parsed": {
                    "gate_decision": str(gate.get("decision", "executed") or "executed"),
                    "gate_decision_reason": str(gate.get("reason", "") or ""),
                    "reason_codes": list(gate.get("reason_codes", [])) if isinstance(gate.get("reason_codes"), list) else [],
                    "skipped": str(gate.get("decision", "executed") or "executed") == "skipped",
                },
                "model": None,
                "tokens_in": None,
                "tokens_out": None,
                "retry_count": 0,
                "ok": True,
                "error_stage": "",
                "error": "",
                "queue_ms": None,
                "ttfb_ms": None,
                "gate_rule_id": str(gate.get("gate_rule_id", "") or ""),
                "gate_version": str(gate.get("gate_version", "v1") or "v1"),
                "gate_inputs": _safe_json(gate.get("gate_inputs")),
                "gate_decision": str(gate.get("decision", "executed") or "executed"),
                "gate_reason": str(gate.get("reason", "") or ""),
                "gate_reason_codes": list(gate.get("reason_codes", [])) if isinstance(gate.get("reason_codes"), list) else [],
                "input_capture_state": "captured" if gate.get("gate_inputs") is not None else "not_captured",
                "output_capture_state": "captured",
                "input_truncation": None,
                "output_truncation": None,
            }
        )
    return out


def _inject_skipped_llm_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = {str(node.get("node_name", "")) for node in nodes if isinstance(node, dict)}
    injected: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or str(node.get("node_type")) != "gate":
            continue
        gate_name = str(node.get("node_name", ""))
        decision = str(node.get("gate_decision", "executed") or "executed")
        if decision != "skipped":
            continue
        target_llm = ""
        reason_codes = list(node.get("gate_reason_codes", [])) if isinstance(node.get("gate_reason_codes"), list) else []
        if gate_name == "planner_gate":
            target_llm = "planner_llm"
            reason_codes = [*reason_codes, "skipped_by_planner_gate"]
        elif gate_name == "belief_gate":
            target_llm = "belief_llm"
            reason_codes = [*reason_codes, "skipped_by_belief_gate"]
        elif gate_name == "world_gate":
            target_llm = "world_extractor_llm"
            reason_codes = [*reason_codes, "skipped_by_world_gate"]
        if not target_llm or target_llm in existing:
            continue
        ts = str(node.get("ended_at") or node.get("started_at") or "")
        injected.append(
            {
                "trace_id": node.get("trace_id"),
                "session_id": node.get("session_id"),
                "turn_idx": node.get("turn_idx"),
                "node_id": f"synthetic-{target_llm}-{len(injected)}",
                "node_name": target_llm,
                "node_type": "llm_call",
                "status": "skipped",
                "started_at": ts,
                "ended_at": ts,
                "latency_ms": 0,
                "sequence_index": 0,
                "input_prompt_rendered": "",
                "input_payload_raw": None,
                "output_text_rendered": "",
                "output_text_raw": None,
                "output_payload_raw": {
                    "gate_decision_reason": str(node.get("gate_reason", "") or ""),
                    "reason_codes": reason_codes,
                    "skipped_by_gate": gate_name,
                },
                "output_payload_parsed": {
                    "gate_decision_reason": str(node.get("gate_reason", "") or ""),
                    "reason_codes": reason_codes,
                    "skipped_by_gate": gate_name,
                },
                "model": None,
                "tokens_in": None,
                "tokens_out": None,
                "retry_count": 0,
                "ok": False,
                "error_stage": "skipped_by_gate",
                "error": str(node.get("gate_reason", "") or ""),
                "queue_ms": None,
                "ttfb_ms": None,
                "gate_rule_id": "",
                "gate_version": "",
                "gate_inputs": None,
                "gate_decision": "",
                "gate_reason": "",
                "gate_reason_codes": [],
                "input_capture_state": "not_captured",
                "output_capture_state": "not_captured",
                "input_truncation": None,
                "output_truncation": None,
            }
        )
        existing.add(target_llm)
    if not injected:
        return nodes
    return [*nodes, *injected]


def _sort_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = list(enumerate(nodes))

    def _key(item: tuple[int, dict[str, Any]]) -> tuple[float, float, str, int]:
        pos, node = item
        start_dt = _parse_ts(node.get("started_at"))
        end_dt = _parse_ts(node.get("ended_at"))
        start_v = start_dt.timestamp() if start_dt else float("inf")
        end_v = end_dt.timestamp() if end_dt else float("inf")
        return (start_v, end_v, str(node.get("node_name", "")), pos)

    indexed.sort(key=_key)
    out: list[dict[str, Any]] = []
    for seq, (_, node) in enumerate(indexed):
        node_out = dict(node)
        node_out["sequence_index"] = seq
        redacted_node = _apply_redaction(node_out)
        if redacted_node.get("redaction_applied"):
            if redacted_node.get("input_payload_raw") is not None:
                redacted_node["input_capture_state"] = "redacted"
            if redacted_node.get("output_payload_raw") is not None:
                redacted_node["output_capture_state"] = "redacted"
        in_tr = redacted_node.get("input_truncation") if isinstance(redacted_node.get("input_truncation"), dict) else {}
        out_tr = redacted_node.get("output_truncation") if isinstance(redacted_node.get("output_truncation"), dict) else {}
        if bool(in_tr.get("truncated", False)):
            redacted_node["input_capture_state"] = "truncated"
        if bool(out_tr.get("truncated", False)):
            redacted_node["output_capture_state"] = "truncated"
        out.append(redacted_node)
    return out


def build_livetrace2_event(*, user_id: str, session_id: str, session: SessionState, trace_index: int, trace_item: dict[str, Any]) -> dict[str, Any]:
    runtime = _safe_dict(trace_item.get("trace_runtime"))
    turn_idx = int(trace_item.get("turn", 0) or 0)
    trace_id = f"{user_id}:{session_id}:{turn_idx}:{trace_index}"
    turn_id = f"{session_id}:{turn_idx}"

    nodes = _build_llm_nodes(trace_id, session_id, turn_idx, runtime)
    nodes.extend(_build_gate_nodes(trace_id, session_id, turn_idx, runtime))
    nodes = _inject_skipped_llm_nodes(nodes)
    nodes = _sort_nodes(nodes)

    for i, node in enumerate(nodes):
        node["prev_node_id"] = nodes[i - 1]["node_id"] if i > 0 else None
        node["next_node_ids"] = [nodes[i + 1]["node_id"]] if i + 1 < len(nodes) else []

    turn_started = str(trace_item.get("t_turn_start", "") or "")
    turn_ended = str(trace_item.get("t_after_graph", "") or "")
    if not turn_started and nodes:
        turn_started = str(nodes[0].get("started_at", "") or "")
    if not turn_ended and nodes:
        turn_ended = str(nodes[-1].get("ended_at", "") or "")

    total_latency = sum(int(node.get("latency_ms", 0) or 0) for node in nodes)

    return {
        "trace_schema_version": "livetrace2-v1",
        "trace_id": trace_id,
        "turn_id": turn_id,
        "user_id": user_id,
        "session_id": session_id,
        "trace_index": trace_index,
        "turn_idx": turn_idx,
        "started_at": turn_started,
        "ended_at": turn_ended,
        "total_latency_ms": total_latency,
        "updated_at": session.last_updated.isoformat(),
        "input_message": trace_item.get("user_message", ""),
        "final_reply": trace_item.get("assistant_reply", ""),
        "world_parallelism": trace_item.get("world_parallelism") if isinstance(trace_item.get("world_parallelism"), dict) else {},
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
