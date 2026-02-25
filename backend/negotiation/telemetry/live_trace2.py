from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any


_LIVETRACE2_RING: deque[dict[str, Any]] = deque(maxlen=300)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _llm_node_from_meta(name: str, meta: dict[str, Any]) -> dict[str, Any]:
    started = meta.get("start_ts")
    ended = meta.get("end_ts")
    return {
        "node_name": name,
        "node_type": "llm",
        "status": "ok" if not meta.get("error") else "error",
        "latency_ms": _safe_int(meta.get("latency_ms"), 0),
        "started_at": started or "",
        "ended_at": ended or "",
        "input_prompt_rendered": str(meta.get("input_prompt_rendered") or ""),
        "input_payload_raw": meta.get("input_payload_raw"),
        "output_text_rendered": str(meta.get("output_text_rendered") or ""),
        "output_payload_raw": meta.get("output_payload_raw"),
        "input_capture_state": "captured" if meta.get("input_prompt_rendered") or meta.get("input_payload_raw") is not None else "not_captured",
        "output_capture_state": "captured" if meta.get("output_text_rendered") or meta.get("output_payload_raw") is not None else "not_captured",
    }


def _gate_node_from_meta(name: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_name": name,
        "node_type": "gate",
        "status": str(meta.get("decision") or "missing"),
        "latency_ms": _safe_int(meta.get("latency_ms"), 0),
        "started_at": str(meta.get("start_ts") or ""),
        "ended_at": str(meta.get("end_ts") or ""),
        "gate_inputs": meta.get("gate_inputs") if isinstance(meta.get("gate_inputs"), dict) else {},
        "gate_decision": str(meta.get("decision") or ""),
        "gate_reason": str(meta.get("reason") or ""),
        "gate_reason_codes": list(meta.get("reason_codes") or []) if isinstance(meta.get("reason_codes"), list) else [],
        "input_capture_state": "captured" if isinstance(meta.get("gate_inputs"), dict) else "not_captured",
        "output_capture_state": "captured" if meta.get("decision") else "not_captured",
    }


def _find_runtime_llm(runtime: dict[str, Any], name: str) -> dict[str, Any]:
    llm_calls = runtime.get("llm_calls") if isinstance(runtime.get("llm_calls"), list) else []
    for item in reversed(llm_calls):
        if isinstance(item, dict) and str(item.get("name") or "") == name:
            return item
    return {}


def _find_runtime_gate(runtime: dict[str, Any], name: str) -> dict[str, Any]:
    gate_events = runtime.get("gate_events") if isinstance(runtime.get("gate_events"), list) else []
    for item in reversed(gate_events):
        if isinstance(item, dict) and str(item.get("name") or "") == name:
            return item
    return {}


def _build_world_judge_node(runtime: dict[str, Any], payload: dict[str, Any], world_meta: dict[str, Any]) -> dict[str, Any] | None:
    runtime_node = _find_runtime_llm(runtime, "world_judge_llm")
    if runtime_node:
        node = _llm_node_from_meta("world_judge_llm", runtime_node)
    elif payload.get("semantic_judge") is not None:
        node = {
            "node_name": "world_judge_llm",
            "node_type": "llm",
            "status": "ok",
            "latency_ms": _safe_int(world_meta.get("judge_latency_ms"), 0),
            "started_at": str(world_meta.get("judge_start_ts") or ""),
            "ended_at": str(world_meta.get("judge_end_ts") or ""),
            "input_capture_state": "not_captured",
            "output_capture_state": "captured",
        }
    else:
        return None

    judge_input = str(world_meta.get("judge_input_prompt_rendered") or "")
    if judge_input:
        node["input_prompt_rendered"] = judge_input
        node["input_capture_state"] = "captured"

    judge_raw_output = str(world_meta.get("judge_output_text_rendered") or "")
    semantic_judge = payload.get("semantic_judge") if isinstance(payload.get("semantic_judge"), dict) else None
    if judge_raw_output or semantic_judge is not None:
        node["output_payload_parsed"] = {
            "llm_raw_output_text": judge_raw_output,
            "semantic_judge_final": semantic_judge or {},
        }
        node["output_text_rendered"] = ""
        node["output_capture_state"] = "captured"

    return node


def _build_executor_node(runtime: dict[str, Any], executor_output: dict[str, Any]) -> dict[str, Any] | None:
    runtime_node = _find_runtime_llm(runtime, "executor_llm")
    if runtime_node:
        node = _llm_node_from_meta("executor_llm", runtime_node)
    elif executor_output:
        node = {
            "node_name": "executor_llm",
            "node_type": "llm",
            "status": "ok",
            "latency_ms": 0,
            "started_at": "",
            "ended_at": "",
            "input_capture_state": "not_captured",
            "output_capture_state": "not_captured",
        }
    else:
        return None

    if executor_output:
        node["output_payload_parsed"] = {
            "final_executor_output": executor_output,
            "llm_raw_output_text": str(node.get("output_text_rendered") or ""),
            "llm_raw_output_payload": node.get("output_payload_raw"),
        }
        node["output_text_rendered"] = ""
        node["output_payload_raw"] = executor_output
        node["output_capture_state"] = "captured"

    return node


def build_semantic_turn_model(
    *,
    user_id: str,
    session_id: str,
    turn_count: int,
    trace_index: int,
    payload: dict[str, Any],
    ts: str,
) -> dict[str, Any]:
    runtime = payload.get("trace_runtime") if isinstance(payload.get("trace_runtime"), dict) else {}
    world_meta = payload.get("world_judge_meta") if isinstance(payload.get("world_judge_meta"), dict) else {}
    planner_meta = payload.get("planner_meta") if isinstance(payload.get("planner_meta"), dict) else {}
    executor_output = payload.get("executor_output") if isinstance(payload.get("executor_output"), dict) else {}

    user_message = str(payload.get("user_message") or payload.get("input_message") or "").strip()
    assistant_message = str(payload.get("assistant_message") or executor_output.get("response_text") or payload.get("final_reply") or "").strip()

    nodes: list[dict[str, Any]] = []

    world_gate = _find_runtime_gate(runtime, "world_gate")
    if world_gate:
        nodes.append(_gate_node_from_meta("world_gate", world_gate))

    planner_gate = _find_runtime_gate(runtime, "planner_gate")
    if planner_gate:
        nodes.append(_gate_node_from_meta("planner_gate", planner_gate))

    world_node = _build_world_judge_node(runtime, payload, world_meta)
    if world_node is not None:
        nodes.append(world_node)

    planner_llm = _find_runtime_llm(runtime, "planner_llm")
    if planner_llm:
        nodes.append(_llm_node_from_meta("planner_llm", planner_llm))
    elif payload.get("planner_semantic_output") is not None:
        nodes.append(
            {
                "node_name": "planner_llm",
                "node_type": "llm",
                "status": "ok" if not planner_meta.get("planner_failed") else "error",
                "latency_ms": _safe_int(planner_meta.get("planner_latency_ms"), 0),
                "started_at": str(planner_meta.get("planner_start_ts") or ""),
                "ended_at": str(planner_meta.get("planner_end_ts") or ""),
                "output_payload_raw": payload.get("planner_semantic_output"),
                "input_capture_state": "not_captured",
                "output_capture_state": "captured",
            }
        )

    executor_node = _build_executor_node(runtime, executor_output)
    if executor_node is not None:
        nodes.append(executor_node)

    started_candidates = [n.get("started_at") for n in nodes if str(n.get("started_at") or "").strip()]
    ended_candidates = [n.get("ended_at") for n in nodes if str(n.get("ended_at") or "").strip()]
    started_at = min(started_candidates) if started_candidates else ts
    ended_at = max(ended_candidates) if ended_candidates else ts
    total_latency_ms = 0
    for n in nodes:
        try:
            total_latency_ms += int(n.get("latency_ms") or 0)
        except Exception:
            continue

    return {
        "user_id": str(user_id or ""),
        "session_id": str(session_id or ""),
        "trace_index": int(trace_index or 0),
        "turn_idx": _safe_int(payload.get("turn_idx"), turn_count),
        "turn_count": int(turn_count or 0),
        "started_at": started_at,
        "ended_at": ended_at,
        "total_latency_ms": total_latency_ms,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "final_reply": assistant_message,
        "nodes": nodes,
        "payload": payload,
    }


def build_livetrace2_event(
    *,
    user_id: str,
    session_id: str,
    session: Any,
    trace_index: int,
    trace_item: dict,
) -> dict:
    base = dict(trace_item or {}) if isinstance(trace_item, dict) else {}
    turn_count = 0
    if session is not None:
        turn_count = int(getattr(session, "turn_count", 0) or 0)
    now_ts = datetime.utcnow().isoformat() + "Z"

    if isinstance(base.get("nodes"), list):
        event = dict(base)
        event.setdefault("user_id", str(user_id or ""))
        event.setdefault("session_id", str(session_id or ""))
        event.setdefault("trace_index", int(trace_index or 0))
        event.setdefault("turn_count", turn_count)
        event.setdefault("ts", now_ts)
        return event

    semantic_event = build_semantic_turn_model(
        user_id=user_id,
        session_id=session_id,
        turn_count=turn_count,
        trace_index=trace_index,
        payload=base,
        ts=now_ts,
    )
    semantic_event["ts"] = now_ts
    return semantic_event


def append_livetrace2_event(event: dict[str, Any]) -> None:
    if isinstance(event, dict):
        _LIVETRACE2_RING.append(dict(event))


def list_recent_livetrace2_events(limit: int = 10) -> list[dict]:
    safe_limit = max(0, int(limit or 0))
    if safe_limit == 0:
        return []
    return list(_LIVETRACE2_RING)[-safe_limit:]
