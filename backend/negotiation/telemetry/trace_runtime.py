from __future__ import annotations

from datetime import datetime, timezone
import os
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
    }


def ensure_trace_runtime(state: dict[str, Any]) -> dict[str, Any]:
    runtime = state.get("trace_runtime")
    if not isinstance(runtime, dict):
        runtime = init_trace_runtime()
        state["trace_runtime"] = runtime
    runtime.setdefault("nodes", {})
    runtime.setdefault("llm_calls", [])
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
) -> None:
    end = time.perf_counter()
    latency_ms = max(1, int((end - started) * 1000))
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
) -> None:
    runtime = ensure_trace_runtime(state)
    call = {
        "name": str(name)[:48],
        "node": str(node)[:48],
        "start_ts": _utc_now_iso(),
        "end_ts": _utc_now_iso(),
        "latency_ms": max(1, int(latency_ms or 0)),
        "model": (str(model)[:80] if model else None),
        "tokens_in": tokens_in if isinstance(tokens_in, int) and tokens_in >= 0 else None,
        "tokens_out": tokens_out if isinstance(tokens_out, int) and tokens_out >= 0 else None,
        "retry_count": max(0, int(retry_count or 0)),
        "ok": bool(ok),
        "error_stage": str(error_stage or "")[:48],
        "error": str(error or "")[:240],
    }
    runtime["llm_calls"].append(call)
    runtime["llm_calls"] = runtime["llm_calls"][:12]
    record_node_phase_ms(state, node, "llm_ms", call["latency_ms"])


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
