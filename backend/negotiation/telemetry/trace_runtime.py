from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import hashlib
import time
from typing import Any

NODE_NAMES = (
    "world_updater",
    "belief_updater",
    "policy_progress",
    "phase_policy_planner",
    "progress_updater",
    "executor",
)


def _default_node_timing() -> dict[str, Any]:
    return {
        "total_ms": 0,
        "gates_ms": 0,
        "normalize_merge_diff_ms": 0,
        "llm_ms": 0,
        "entered": False,
        "skipped": False,
    }


def init_trace_runtime() -> dict[str, Any]:
    return {
        "nodes": {name: _default_node_timing() for name in NODE_NAMES},
        "llm_calls": [],
        "gate_events": [],
    }


def ensure_trace_runtime(state: dict[str, Any]) -> dict[str, Any]:
    runtime = state.get("trace_runtime")
    if not isinstance(runtime, dict):
        runtime = init_trace_runtime()
        state["trace_runtime"] = runtime
    runtime.setdefault("nodes", {})
    runtime.setdefault("llm_calls", [])
    runtime.setdefault("gate_events", [])
    for name in NODE_NAMES:
        runtime["nodes"].setdefault(name, _default_node_timing())
    return runtime


def start_node_timer(state: dict[str, Any], node: str) -> float:
    runtime = ensure_trace_runtime(state)
    node_data = runtime["nodes"].setdefault(node, _default_node_timing())
    node_data["entered"] = True
    return time.perf_counter()


def finish_node_timer(state: dict[str, Any], node: str, started: float, *, skipped: bool = False) -> None:
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    runtime = ensure_trace_runtime(state)
    node_data = runtime["nodes"].setdefault(node, _default_node_timing())
    node_data["total_ms"] = elapsed_ms
    node_data["skipped"] = bool(skipped)


def record_node_phase_ms(state: dict[str, Any], node: str, phase_key: str, elapsed_ms: int) -> None:
    runtime = ensure_trace_runtime(state)
    node_data = runtime["nodes"].setdefault(node, _default_node_timing())
    node_data[phase_key] = max(0, int(node_data.get(phase_key, 0) or 0) + int(elapsed_ms or 0))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _truncate_text(value: str, max_chars: int = 12000) -> tuple[str, dict[str, Any]]:
    text = str(value or "")
    original_bytes = len(text.encode("utf-8"))
    if len(text) <= max_chars:
        return text, {
            "truncated": False,
            "original_bytes": original_bytes,
            "kept_bytes": original_bytes,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
        }
    kept = text[:max_chars]
    kept_bytes = len(kept.encode("utf-8"))
    return kept, {
        "truncated": True,
        "original_bytes": original_bytes,
        "kept_bytes": kept_bytes,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }

def record_llm_call(
    state: dict[str, Any],
    *,
    name: str,
    node: str,
    started: float,
    ok: bool,
    model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    retry_count: int = 0,
    error_stage: str = "",
    error: str = "",
    input_prompt_rendered: str = "",
    output_text_rendered: str = "",
    input_payload_raw: Any | None = None,
    output_payload_raw: Any | None = None,
    status: str | None = None,
) -> None:
    end_perf = time.perf_counter()
    end_wall = datetime.now(timezone.utc)
    latency_ms = max(1, int((end_perf - started) * 1000))
    start_wall = end_wall - timedelta(milliseconds=latency_ms)
    record_llm_call_ms(
        state,
        name=name,
        node=node,
        latency_ms=latency_ms,
        ok=ok,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        retry_count=retry_count,
        error_stage=error_stage,
        error=error,
        input_prompt_rendered=input_prompt_rendered,
        output_text_rendered=output_text_rendered,
        input_payload_raw=input_payload_raw,
        output_payload_raw=output_payload_raw,
        status=status,
        start_ts=start_wall.isoformat(),
        end_ts=end_wall.isoformat(),
    )


def record_llm_call_ms(
    state: dict[str, Any],
    *,
    name: str,
    node: str,
    latency_ms: int,
    ok: bool,
    model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    retry_count: int = 0,
    error_stage: str = "",
    error: str = "",
    start_ts: str | None = None,
    end_ts: str | None = None,
    queue_ms: int | None = None,
    ttfb_ms: int | None = None,
    input_prompt_rendered: str = "",
    output_text_rendered: str = "",
    input_payload_raw: Any | None = None,
    output_payload_raw: Any | None = None,
    status: str | None = None,
    prompt_variant: str | None = None,
    payload_chars: int | None = None,
    llm_call_count: int | None = None,
) -> None:
    runtime = ensure_trace_runtime(state)
    input_prompt_final, input_prompt_meta = _truncate_text(str(input_prompt_rendered or ""), 12000)
    output_text_final, output_text_meta = _truncate_text(str(output_text_rendered or ""), 12000)
    call = {
        "name": str(name)[:48],
        "node": str(node)[:48],
        "start_ts": str(start_ts or _utc_now_iso()),
        "end_ts": str(end_ts or _utc_now_iso()),
        "latency_ms": max(1, int(latency_ms or 0)),
        "model": (str(model)[:80] if model else None),
        "tokens_in": tokens_in if isinstance(tokens_in, int) and tokens_in >= 0 else None,
        "tokens_out": tokens_out if isinstance(tokens_out, int) and tokens_out >= 0 else None,
        "retry_count": max(0, int(retry_count or 0)),
        "ok": bool(ok),
        "error_stage": str(error_stage or "")[:48],
        "error": str(error or "")[:240],
        "queue_ms": queue_ms if isinstance(queue_ms, int) and queue_ms >= 0 else None,
        "ttfb_ms": ttfb_ms if isinstance(ttfb_ms, int) and ttfb_ms >= 0 else None,
        "input_prompt_rendered": input_prompt_final,
        "output_text_rendered": output_text_final,
        "input_prompt_meta": input_prompt_meta,
        "output_text_meta": output_text_meta,
        "input_payload_raw": input_payload_raw,
        "output_payload_raw": output_payload_raw,
        "status": str(status or ("ok" if bool(ok) else "error"))[:24],
        "prompt_variant": str(prompt_variant or "")[:12],
        "payload_chars": payload_chars if isinstance(payload_chars, int) and payload_chars >= 0 else None,
        "llm_call_count": llm_call_count if isinstance(llm_call_count, int) and llm_call_count >= 0 else None,
    }
    runtime["llm_calls"].append(call)
    runtime["llm_calls"] = runtime["llm_calls"][:12]
    record_node_phase_ms(state, node, "llm_ms", call["latency_ms"])



def record_gate_event(
    state: dict[str, Any],
    *,
    name: str,
    node: str,
    decision: str,
    reason: str = "",
    reason_codes: list[str] | None = None,
    gate_inputs: Any | None = None,
    gate_rule_id: str = "",
    gate_version: str = "v1",
    started: float | None = None,
    started_ts: str | None = None,
    ended_ts: str | None = None,
) -> None:
    runtime = ensure_trace_runtime(state)
    now_perf = time.perf_counter()
    latency_ms = 0
    if started is not None:
        latency_ms = max(0, int((now_perf - float(started)) * 1000))
    start_iso = str(started_ts or _utc_now_iso())
    end_iso = str(ended_ts or _utc_now_iso())
    runtime["gate_events"].append(
        {
            "name": str(name)[:64],
            "node": str(node)[:48],
            "decision": "skipped" if str(decision) == "skipped" else "executed",
            "reason": str(reason or "")[:240],
            "reason_codes": [str(x)[:80] for x in (reason_codes or []) if str(x).strip()][:8],
            "gate_inputs": gate_inputs,
            "gate_rule_id": str(gate_rule_id or "")[:64],
            "gate_version": str(gate_version or "v1")[:24],
            "start_ts": start_iso,
            "end_ts": end_iso,
            "latency_ms": latency_ms,
            "status": "ok",
        }
    )
    runtime["gate_events"] = runtime["gate_events"][:24]
    record_node_phase_ms(state, node, "gates_ms", latency_ms)

def trace_level() -> int:
    raw = os.getenv("TRACE_LEVEL", "1")
    try:
        return max(0, min(3, int(raw)))
    except Exception:
        return 1


def trace_include_internals() -> bool:
    if os.getenv("TRACE_INCLUDE_INTERNALS") is None:
        return trace_level() >= 2
    return os.getenv("TRACE_INCLUDE_INTERNALS", "0") == "1"
